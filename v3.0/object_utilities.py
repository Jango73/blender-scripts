# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Object utilities",
    "author": "Jango73",
    "version": (3, 4),
    "blender": (3, 0, 0),
    "description": "Operations on objects",
    "category": "Object",
}

import bpy
import bmesh
import math
import re
import copy
from datetime import datetime
from mathutils.kdtree import KDTree

# -------------------------------------------------------------------
# Global storage for transform copy/paste
_copied_transform = None

# Global storage for modifier/custom params copy/paste
_copied_modifier_data = None

# -----------------------------------------------------------------------------
# Following two functions are from "blenderartists.org/u/Gorgious" in "object_copy_custom_properties_1_08.py"

def setProperty(obj, name, value, rna, is_overridable):
    if obj is None:
        return

    obj[name] = value
    obj.id_properties_ensure()
    id_properties_ui = obj.id_properties_ui(name)
    id_properties_ui.update_from(rna)
    obj.property_overridable_library_set(f'["{name}"]', is_overridable)

def getProperties(obj):
    if obj is None:
        return tuple()

    obj.id_properties_ensure()

    names = []
    items = obj.items()
    rna_properties = { prop.identifier for prop in obj.bl_rna.properties if prop.is_runtime }

    for k, _ in items:
        if k in rna_properties:
            continue
        names.append(k)

    names = list(set(obj.keys()) - set(('cycles_visibility', 'cycles', '_RNA_UI', 'pov')))
    values = [(name, obj[name], obj.id_properties_ui(name),  obj.is_property_overridable_library(f'["{name}"]')) for name in names]

    return values

# -----------------------------------------------------------------------------

def showMessageBox(title = "Message Box", icon = 'INFO', lines=""):
    myLines=lines
    def draw(self, context):
        for n in myLines:
            self.layout.label(text=n)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

# -----------------------------------------------------------------------------

def printToString(targetString, text, no_newline=False):

    temp = targetString.split("\n")
    if len(temp) > 0:
        if len(temp[-1]) > 200:
            targetString += ("\n")

    if (no_newline):
        targetString += (text)
    else:
        targetString += (text + "\n")

    return targetString

# -----------------------------------------------------------------------------

def purgeAll(self, context):

    deleted = 0
    bpy.ops.outliner.orphans_purge(num_deleted=deleted, do_recursive=True)

    showMessageBox(lines=["All orphans deleted"])

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def diffLines(targetString, sourceName, targetName, lines1, lines2):
    temp = copy.deepcopy(lines1)

    for x in temp:
        if x in lines2:
            lines1.remove(x)
            lines2.remove(x)

    if len(lines1) == 0 and len(lines2) == 0:
        targetString = printToString(targetString, "No difference")
        return targetString

    if len(lines1) > 0:
        targetString = printToString(targetString, "Only in " + sourceName + ":")
        for x in lines1:
            targetString = printToString(targetString, x + " ", no_newline=True)
        targetString = printToString(targetString, "")

    if len(lines2) > 0:
        targetString = printToString(targetString, "Only in " + targetName + ":")
        for x in lines2:
            targetString = printToString(targetString, x + " ", no_newline=True)
        targetString = printToString(targetString, "")

    return targetString

# -----------------------------------------------------------------------------

def diffObjects(self, context):
    lineCount = 0
    diffCount = 0
    sameCount = 0
    targetString = ""
    lines1 = []
    lines2 = []

    target = context.selected_objects[0]

    if target is None:
        return {'CANCELLED'}

    # get active object
    source = context.active_object

    if source is None:
        return {'CANCELLED'}

    if target == source:
        if len(context.selected_objects) < 2:
            return {'CANCELLED'}
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    targetString = printToString(targetString, "")
    targetString = printToString(targetString, "Diff " + source.name + " and " + target.name)
    targetString = printToString(targetString, "")

    if len(source.keys()) > 1 and len(target.keys()) > 1:
        targetString = printToString(targetString, "[ Custom property names ]")

        for p in source.keys():
            lines1.append(p.strip())
        for p in target.keys():
            lines2.append(p.strip())

        lines1.sort()
        lines2.sort()
        targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

        targetString = printToString(targetString, "[ Custom property values ]")

        for p in source.keys():
            lines1.append("" + p.strip() + "=" + str(source.get(p)))
        for p in target.keys():
            lines2.append("" + p.strip() + "=" + str(target.get(p)))

        lines1.sort()
        lines2.sort()
        targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

    try:
        targetString = printToString(targetString, "")
        targetString = printToString(targetString, "[ Vertex groups ]")

        lines1.clear()
        lines2.clear()

        for g in source.vertex_groups:
            lines1.append(g.name.strip())
        for g in target.vertex_groups:
            lines2.append(g.name.strip())

        lines1.sort()
        lines2.sort()
        targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

    except:
        pass

    try:
        targetString = printToString(targetString, "")
        targetString = printToString(targetString, "[ Vertex colors ]")

        lines1.clear()
        lines2.clear()

        for v in source.data.vertex_colors.keys():
            lines1.append(v.strip())
        for v in target.data.vertex_colors.keys():
            lines2.append(v.strip())

        lines1.sort()
        lines2.sort()
        targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

    except:
        pass

    try:
        targetString = printToString(targetString, "")
        targetString = printToString(targetString, "[ Modifiers ]")

        lines1.clear()
        lines2.clear()

        for m in source.modifiers:
            lines1.append(m.name.strip())
        for m in target.modifiers:
            lines2.append(m.name.strip())

        lines1.sort()
        lines2.sort()
        targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

    except:
        pass

    try:
        objectType = getattr(source, 'type', '')

        if objectType in ['ARMATURE']:
            targetString = printToString(targetString, "")
            targetString = printToString(targetString, "[ Bone constraints ]")
            bpy.ops.object.mode_set(mode='POSE')

            lines1.clear()
            lines2.clear()

            for b in source.pose.bones:
                for c in b.constraints:
                    lines1.append(b.name.strip() + ":" + c.name.strip())
            for b in target.pose.bones:
                for c in b.constraints:
                    lines2.append(b.name.strip() + ":" + c.name.strip())

            bpy.ops.object.mode_set(mode='OBJECT')

            lines1.sort()
            lines2.sort()
            targetString = diffLines(targetString, source.name, target.name, lines1, lines2)

    except:
        pass

    showMessageBox(lines=targetString.split("\n"))

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def getMirroredName(name):
    if '.R' in name:
        return name.replace('.R','.L')

    if '.r' in name:
        return name.replace('.r','.l')

    if name.startswith('Right'):
        return name.replace('Right', 'Left')

    if name.startswith('right'):
        return name.replace('right', 'left')

    if '.L' in name:
        return name.replace('.L','.R')

    if '.l' in name:
        return name.replace('.l','.r')

    if name.startswith('Left'):
        return name.replace('Left', 'Right')

    if name.startswith('left'):
        return name.replace('left', 'right')
    
    return ''

# -----------------------------------------------------------------------------

def syncObjectProperties(self, context):
    target = context.selected_objects[0]
    source = context.active_object

    if source is None or target is None:
        return {'CANCELLED'}

    if target == source:
        if len(context.selected_objects) < 2:
            return {'CANCELLED'}
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    values = getProperties(source)

    for value in values:
        if value[0] not in target.keys():
            setProperty(target, value[0], value[1], value[2], value[3])

    self.report({'INFO'}, "Synced " + target.name + " properties with " + source.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def copyMaterialSlots(self, context):
    target = context.selected_objects[0]
    source = context.active_object

    if source is None or target is None:
        return {'CANCELLED'}

    if target == source:
        if len(context.selected_objects) < 2:
            return {'CANCELLED'}
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    if len(source.material_slots) > 0:
        # Assign the material to each slot 
        for c, slot in enumerate(source.material_slots):
            target.material_slots[c].material = source.material_slots[c].material

    self.report({'INFO'}, "Copied " + source.name + " materials to " + target.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def copyObjectPropertyValues(self, context):
    target = context.selected_objects[0]

    if target is None:
        return {'CANCELLED'}

    # get active object
    source = context.active_object

    if source is None:
        return {'CANCELLED'}

    if target == source:
        if len(context.selected_objects) < 2:
            return {'CANCELLED'}
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    for p in source.keys():
        if not p.startswith("_"):
            if p in target.keys():
                target[p] = source.get(p)

    self.report({'INFO'}, "Copied " + source.name + " property values to " + target.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def makeAllPropertiesOverridable(self, context):
    # get active object
    obj = context.active_object

    if obj is None:
        return {'CANCELLED'}

    for pname in obj.keys():
        try:
            qualified_name = "[\"" + pname + "\"]"
            obj.property_overridable_library_set(qualified_name, True)
        except:
            print("Error when processing ", pname)
            pass

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeEmptyVertexGroups(self, context):
    for obj in context.selected_objects:

        obj.update_from_editmode()

        vgroup_used = {i: False for i, k in enumerate(obj.vertex_groups)}
        vgroup_names = {i: k.name for i, k in enumerate(obj.vertex_groups)}
        vgroup_name_list = list(vgroup_names.values())

        for v in obj.data.vertices:
            for g in v.groups:

                mirrored_name = getMirroredName(vgroup_names[g.group])

                if mirrored_name in vgroup_name_list:
                    vgroup_used[g.group] = vgroup_used[vgroup_name_list.index(mirrored_name)]
                else:
                    if g.weight > 0.01:
                        vgroup_used[g.group] = True

        for i, used in sorted(vgroup_used.items(), reverse=True):
            if not used:
                obj.vertex_groups.remove(obj.vertex_groups[i])

        self.report({'INFO'}, "Removed empty groups from " + obj.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeAllModifiers(self, context):
    for obj in context.selected_objects:

        # remove all modifiers
        obj.modifiers.clear()

        self.report({'INFO'}, "Removed all modifiers from " + obj.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def cleanAndApplyModifiers(self, context):
    simulation_types = {'COLLISION', 'FLUID', 'PARTICLE_SYSTEM', 'CLOTH', 'SOFT_BODY', 'DYNAMIC_PAINT', 'EXPLODE', 'OCEAN', 'SURFACE'}

    for obj in context.selected_objects:
        for mod in list(obj.modifiers):
            if mod.type in simulation_types:
                obj.modifiers.remove(mod)
        for mod in list(obj.modifiers):
            if not mod.show_render:
                obj.modifiers.remove(mod)
        for mod in obj.modifiers:
            if mod.show_render and not mod.show_viewport:
                mod.show_viewport = True

    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    original_active = context.view_layer.objects.active
    original_selected = list(context.selected_objects)
    depsgraph = context.evaluated_depsgraph_get()

    for obj in original_selected:
        if len(obj.modifiers) == 0:
            continue

        if obj.type == 'MESH':
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(obj_eval, preserve_all_data_layers=True, depsgraph=depsgraph)
            obj.data = mesh
            obj.modifiers.clear()
        else:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            while obj.modifiers:
                mod = obj.modifiers[0]
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except:
                    try:
                        obj.modifiers.remove(obj.modifiers[mod.name])
                    except:
                        pass

    bpy.ops.object.select_all(action='DESELECT')
    for o in original_selected:
        if o.name in bpy.data.objects:
            o.select_set(True)
    if original_active and original_active.name in bpy.data.objects:
        context.view_layer.objects.active = original_active

    self.report({'INFO'}, "Cleaned and applied modifiers")
    return {'FINISHED'}

def toggleShadowCatcher(self, context):
    toggled_count = 0

    for obj in context.selected_objects:
        if hasattr(obj, "is_shadow_catcher"):
            obj.is_shadow_catcher = not obj.is_shadow_catcher
            toggled_count += 1

    self.report({'INFO'}, "Toggled shadow catcher on " + str(toggled_count) + " selected object(s)")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def copyObjectTransform(self, context):
    global _copied_transform
    obj = context.active_object

    if obj is None:
        self.report({'ERROR'}, "No active object.")
        return {'CANCELLED'}

    _copied_transform = {
        "location": obj.location[:],
        "rotation": obj.rotation_euler[:],
        "scale": obj.scale[:]
    }

    self.report({'INFO'}, f"Copied transform: {obj.location[:]}")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def pasteObjectTransform(self, context):
    global _copied_transform
    obj = context.active_object

    if obj is None:
        self.report({'ERROR'}, "No active object.")
        return {'CANCELLED'}

    if _copied_transform is None:
        self.report({'WARNING'}, "No transform stored. Use 'Copy' first.")
        return {'CANCELLED'}

    obj.location = _copied_transform["location"]
    obj.rotation_euler = _copied_transform["rotation"]
    obj.scale = _copied_transform["scale"]

    self.report({'INFO'}, f"Pasted transform: {obj.location[:]}")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def _sanitize_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(v) for v in value]
    return str(value)

def copyModifierParams(self, context):
    global _copied_modifier_data
    obj = context.active_object

    if obj is None:
        self.report({'ERROR'}, "No active object.")
        return {'CANCELLED'}

    if len(context.selected_objects) != 1:
        self.report({'ERROR'}, "Select exactly one object.")
        return {'CANCELLED'}

    skip_modifier_types = {'CLOTH', 'COLLISION', 'DYNAMIC_PAINT', 'EXPLODE', 'FLUID', 'OCEAN', 'PARTICLE_SYSTEM', 'SOFT_BODY', 'SURFACE'}
    modifier_data = []
    for mod in obj.modifiers:
        if mod.type in skip_modifier_types:
            continue
        safe_types = {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM', 'BOOLEAN_ARRAY', 'INT_ARRAY', 'FLOAT_ARRAY'}
        params = {}
        for prop in mod.bl_rna.properties:
            if prop.identifier in ('name', 'type', 'rna_type', 'show_viewport', 'show_render', 'show_in_editmode', 'show_on_cage', 'show_expanded', 'is_active'):
                continue
            if prop.is_readonly:
                continue
            if prop.type not in safe_types:
                continue
            try:
                value = getattr(mod, prop.identifier)
                if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                    value = list(value)
                params[prop.identifier] = value
            except:
                pass
        input_params = {}
        try:
            mod_keys = mod.keys()
        except TypeError:
            mod_keys = []
        try:
            rna_ui = mod.get("_RNA_UI")
        except TypeError:
            rna_ui = None
        for key in mod_keys:
            if key == '_RNA_UI':
                continue
            try:
                val = mod[key]
                sanitized = _sanitize_value(val)
                is_overridable = mod.is_property_overridable_library(f'["{key}"]')
                entry = {"value": sanitized, "is_overridable": is_overridable}
                if rna_ui and key in rna_ui:
                    entry["rna_ui"] = _sanitize_value(rna_ui[key])
                input_params[key] = entry
            except:
                pass
        modifier_data.append({
            "name": mod.name,
            "type": mod.type,
            "params": params,
            "input_params": input_params,
        })

    custom_props = []
    for name, value, rna, is_overridable in getProperties(obj):
        try:
            sanitized = _sanitize_value(value)
            custom_props.append({"name": name, "value": sanitized})
        except:
            pass

    _copied_modifier_data = {
        "modifiers": modifier_data,
        "custom_properties": custom_props,
    }

    count_mods = len(modifier_data)
    count_cp = len(custom_props)
    self.report({'INFO'}, f"Copied {count_mods} modifier(s) and {count_cp} custom propert{'y' if count_cp == 1 else 'ies'} from {obj.name}")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def pasteModifierParams(self, context):
    global _copied_modifier_data
    obj = context.active_object

    if obj is None:
        self.report({'ERROR'}, "No active object.")
        return {'CANCELLED'}

    if len(context.selected_objects) != 1:
        self.report({'ERROR'}, "Select exactly one object.")
        return {'CANCELLED'}

    if _copied_modifier_data is None:
        self.report({'WARNING'}, "No modifier data stored. Use 'Copy' first.")
        return {'CANCELLED'}

    used_names = set()
    skip_modifier_types = {'CLOTH', 'COLLISION', 'DYNAMIC_PAINT', 'EXPLODE', 'FLUID', 'OCEAN', 'PARTICLE_SYSTEM', 'SOFT_BODY', 'SURFACE'}

    for idx, src_mod in enumerate(_copied_modifier_data["modifiers"]):
        target_mod = None

        for m in obj.modifiers:
            if m.type in skip_modifier_types:
                continue
            if m.name.lower() == src_mod["name"].lower() and m.name not in used_names:
                target_mod = m
                break

        if target_mod is None:
            if idx < len(obj.modifiers):
                m = obj.modifiers[idx]
                if m.type in skip_modifier_types:
                    continue
                if m.type == src_mod["type"] and m.name not in used_names:
                    target_mod = m

        if target_mod is None:
            continue

        used_names.add(target_mod.name)

        safe_types = {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM', 'BOOLEAN_ARRAY', 'INT_ARRAY', 'FLOAT_ARRAY'}
        skip_props = {'show_viewport', 'show_render', 'show_in_editmode', 'show_on_cage', 'show_expanded', 'is_active'}
        for prop_name, prop_value in src_mod["params"].items():
            if prop_name in skip_props:
                continue
            rna_prop = target_mod.bl_rna.properties.get(prop_name)
            if rna_prop is None or rna_prop.type not in safe_types:
                continue
            try:
                setattr(target_mod, prop_name, prop_value)
            except:
                pass

        for iname, ientry in src_mod.get("input_params", {}).items():
            try:
                target_mod[iname] = ientry["value"]
                if "rna_ui" in ientry:
                    target_mod.id_properties_ui(iname).update_from(ientry["rna_ui"])
                target_mod.property_overridable_library_set(f'["{iname}"]', ientry.get("is_overridable", True))
            except:
                pass

    for cp in _copied_modifier_data["custom_properties"]:
        try:
            obj[cp["name"]] = cp["value"]
        except:
            pass

    count_mods = len(_copied_modifier_data["modifiers"])
    count_cp = len(_copied_modifier_data["custom_properties"])
    self.report({'INFO'}, f"Pasted {count_mods} modifier(s) and {count_cp} custom propert{'y' if count_cp == 1 else 'ies'} to {obj.name}")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeKeyframesByChannel(self, context, channel):
    for obj in context.selected_objects:

        if obj.animation_data:
            action = obj.animation_data.action
            if action:
                for fc in action.fcurves:
                    if fc.data_path.endswith(channel):
                        try:
                            obj.keyframe_delete(fc.data_path)
                        except TypeError:
                            print(fc.data_path + " channel does not exist. Ignoring.")

        self.report({'INFO'}, "Removed " + channel + " type keyframes from " + obj.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def updateCommonMesh(self, context):
    target = context.selected_objects[0]
    source = context.active_object

    if source is None or target is None:
        return {'CANCELLED'}

    if target == source:
        if len(context.selected_objects) < 2:
            return {'CANCELLED'}
        target = context.selected_objects[1]

    if target is None:
        return {'CANCELLED'}

    if source.type != 'MESH' or target.type != 'MESH':
        self.report({'ERROR'}, "Both objects must be meshes")
        return {'CANCELLED'}

    vg = source.vertex_groups.get("Common")
    if vg is None:
        self.report({'ERROR'}, "No 'Common' vertex group found on source")
        return {'CANCELLED'}

    prev_mode = context.mode
    if prev_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')

    # Step 1-3: Duplicate Common faces from source and separate into temp
    source.select_set(True)
    context.view_layer.objects.active = source

    names_before = set(o.name for o in bpy.data.objects)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type='VERT')

    source.vertex_groups.active_index = vg.index
    bpy.ops.object.vertex_group_select()

    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.duplicate()
    bpy.ops.mesh.separate(type='SELECTED')

    bpy.ops.object.mode_set(mode='OBJECT')

    names_after = set(o.name for o in bpy.data.objects)
    new_names = names_after - names_before
    if not new_names:
        self.report({'ERROR'}, "Could not create temporary mesh")
        return {'CANCELLED'}
    temp = bpy.data.objects[new_names.pop()]
    temp.name = "temp"

    # Remove all modifiers from temp
    temp.modifiers.clear()

    # Step 4: Delete Common faces from target
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    context.view_layer.objects.active = target

    vg_target = target.vertex_groups.get("Common")
    if vg_target:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='VERT')

        target.vertex_groups.active_index = vg_target.index
        bpy.ops.object.vertex_group_select()

        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.delete(type='FACE')

        bpy.ops.object.mode_set(mode='OBJECT')

    # Step 5: Join temp with target
    bpy.ops.object.select_all(action='DESELECT')
    temp.select_set(True)
    target.select_set(True)
    context.view_layer.objects.active = target
    bpy.ops.object.join()

    # Step 6: Merge by distance
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    context.view_layer.objects.active = target

    self.report({'INFO'}, f"mesh common data copied from {source.name} to {target.name}")
    return {'FINISHED'}

# -----------------------------------------------------------------------------

def cleanUpMaterialsAndImages(context):
    # iterate over all materials in the file
    for material in bpy.data.materials:

        # don't do anything if the material has any users.
        if material.users:
            continue

        # remove the material otherwise
        bpy.data.materials.remove(material)

    # iterate over all images in the file
    for image in bpy.data.images:

        # don't do anything if the image has any users.
        if image.users:
            continue

        # remove the image otherwise
        bpy.data.images.remove(image)

    return {'FINISHED'}

# -----------------------------------------------------------------------------
# FIX : This creates a mess with the edges of faces

def rotateFaceVertexIndices(context):
    # If in edit mode, switch to object mode and switch back at the end
    was_in_edit_mode = False

    for obj in context.selected_objects:
        if obj.type == 'MESH':

            if obj.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
                was_in_edit_mode = True

            me = obj.data

            for poly in me.polygons:
                if not poly.select:
                    continue

                # Get loops for this poly
                # Loop = corner of a poly
                loop_start = poly.loop_start
                loop_end = loop_start + poly.loop_total
                loops = [me.loops[loopi] for loopi in range(loop_start, loop_end)]

                # Get vertex indices for each loop
                vidxs = [loop.vertex_index for loop in loops]

                # Shift
                vidxs = vidxs[1:] + vidxs[0:1]

                # Write back
                for i, loop in enumerate(loops):
                    loop.vertex_index = vidxs[i]

            # Not sure if you need this
            me.update()

            if was_in_edit_mode:
                bpy.ops.object.mode_set(mode='EDIT')

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def selectMergeByDistanceVerts(self, context, threshold):
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        self.report({'ERROR'}, "Active object is not a mesh")
        return {'CANCELLED'}

    me = obj.data
    bm = bmesh.from_edit_mesh(me)

    bm.verts.ensure_lookup_table()

    for v in bm.verts:
        v.select = False

    if len(bm.verts) == 0:
        bmesh.update_edit_mesh(me)
        self.report({'WARNING'}, "No vertices in mesh")
        return {'CANCELLED'}

    tree = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        tree.insert(v.co, i)
    tree.balance()

    selected_indices = set()
    for i, v in enumerate(bm.verts):
        neighbors = list(tree.find_range(v.co, threshold))
        if len(neighbors) > 1:
            selected_indices.add(i)
            for (co, idx, dist) in neighbors:
                if idx != i:
                    selected_indices.add(idx)

    for i in selected_indices:
        bm.verts[i].select = True

    bmesh.update_edit_mesh(me)

    count = len(selected_indices)
    if count == 0:
        self.report({'INFO'}, "No vertices to merge found")
    else:
        self.report({'INFO'}, f"Selected {count} vertice(s) that would be merged")

    return {'FINISHED'}

# -----------------------------------------------------------------------------
# Operators

class OBJECT_OT_PurgeAll(bpy.types.Operator):
    """Purge all"""
    bl_idname = "object.purge_all"
    bl_label = "Purge all orphans"
    bl_description = "Purges all orphan data"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return purgeAll(self, context)

class OBJECT_OT_HideAllParticles(bpy.types.Operator):
    """Hide all particles"""
    bl_idname = "object.hide_all_particles"
    bl_label = "Hide all particles"
    bl_description = "Hide all particles"
    bl_options = {'REGISTER'}

    def execute(self, context):
        for object in bpy.data.objects:
            if bpy.context.scene in object.users_scene:
                for modifier in object.modifiers:
                    if modifier.type == 'PARTICLE_SYSTEM':
                        modifier.show_viewport = False
        return {'FINISHED'}

class OBJECT_OT_ShowAllParticles(bpy.types.Operator):
    """Show all particles"""
    bl_idname = "object.show_all_particles"
    bl_label = "Show all particles"
    bl_description = "Show all particles"
    bl_options = {'REGISTER'}

    def execute(self, context):
        for object in bpy.data.objects:
            if bpy.context.scene in object.users_scene:
                for modifier in object.modifiers:
                    if modifier.type == 'PARTICLE_SYSTEM':
                        modifier.show_viewport = True
        return {'FINISHED'}

class OBJECT_OT_DiffObjectData(bpy.types.Operator):
    """Diff Object Data"""
    bl_idname = "object.diff_object_data"
    bl_label = "Diff object data"
    bl_description = "Shows difference in object data"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return diffObjects(self, context)

class OBJECT_OT_SyncObjectProperties(bpy.types.Operator):
    """Sync Object Properties"""
    bl_idname = "object.sync_object_properties"
    bl_label = "Sync object properties"
    bl_description = "Synchronizes the properties of an object with another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return syncObjectProperties(self, context)

class OBJECT_OT_CopyObjectPropertyValues(bpy.types.Operator):
    """Copy Object Property Values"""
    bl_idname = "object.copy_object_property_values"
    bl_label = "Copy object property values"
    bl_description = "Copies the custom property values of an object to another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyObjectPropertyValues(self, context)

class OBJECT_OT_CopyObjectMaterials(bpy.types.Operator):
    """Copy Object Materials"""
    bl_idname = "object.copy_object_materials"
    bl_label = "Copy object materials"
    bl_description = "Copies the materials of an object to another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyMaterialSlots(self, context)

class OBJECT_OT_MakeAllPropertiesOverridable(bpy.types.Operator):
    """Make All Properties Overridable"""
    bl_idname = "object.make_all_properties_overridable"
    bl_label = "Make all properties overridable"
    bl_description = "Makes all properties overridable"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return makeAllPropertiesOverridable(self, context)

class OBJECT_OT_RemoveEmptyVertexGroups(bpy.types.Operator):
    """Remove Empty Vertex Groups"""
    bl_idname = "object.remove_empty_vertex_groups"
    bl_label = "Remove empty vertex groups"
    bl_description = "Removes empty vertex groups"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeEmptyVertexGroups(self, context)

class OBJECT_OT_RemoveAllModifiers(bpy.types.Operator):
    """Remove All Modifiers"""
    bl_idname = "object.remove_all_modifiers"
    bl_label = "Remove all modifiers"
    bl_description = "Removes all modifiers"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeAllModifiers(self, context)

class OBJECT_OT_UpdateCommonMesh(bpy.types.Operator):
    """Update Common Mesh"""
    bl_idname = "object.update_common_mesh"
    bl_label = "Update common mesh"
    bl_description = "Updates the common mesh based on vertex group 'Common'"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return updateCommonMesh(self, context)

class OBJECT_OT_CleanAndApplyModifiers(bpy.types.Operator):
    """Clean and Apply Modifiers"""
    bl_idname = "object.clean_and_apply_modifiers"
    bl_label = "Clean and apply modifiers"
    bl_description = "Removes all simulation systems, removes non-render modifiers, and applies remaining modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return cleanAndApplyModifiers(self, context)

class OBJECT_OT_ToggleShadowCatcher(bpy.types.Operator):
    """Toggle Shadow Catcher"""
    bl_idname = "object.toggle_shadow_catcher"
    bl_label = "Toggle shadow catcher"
    bl_description = "Toggles Shadow Catcher on all selected objects"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return toggleShadowCatcher(self, context)

class OBJECT_OT_CopyObjectTransform(bpy.types.Operator):
    """Copy Object Transform"""
    bl_idname = "object.copy_object_transform"
    bl_label = "Copy object transform"
    bl_description = "Copies the active object's location, rotation and scale to memory"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyObjectTransform(self, context)

class OBJECT_OT_PasteObjectTransform(bpy.types.Operator):
    """Paste Object Transform"""
    bl_idname = "object.paste_object_transform"
    bl_label = "Paste object transform"
    bl_description = "Pastes location, rotation and scale to the active object from memory"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return pasteObjectTransform(self, context)

class OBJECT_OT_CopyModifierParams(bpy.types.Operator):
    """Copy modifier and custom params"""
    bl_idname = "object.copy_modifier_params"
    bl_label = "Copy modifier and custom params"
    bl_description = "Copies all modifier parameters and custom properties of the active object to memory"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return copyModifierParams(self, context)

class OBJECT_OT_PasteModifierParams(bpy.types.Operator):
    """Paste modifier and custom params"""
    bl_idname = "object.paste_modifier_params"
    bl_label = "Paste modifier and custom params"
    bl_description = "Pastes all modifier parameters and custom properties to the active object from memory"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return pasteModifierParams(self, context)

class OBJECT_OT_RemoveLocationKeyframes(bpy.types.Operator):
    """RemoveLocationKeyframes"""
    bl_idname = "object.remove_location_keyframes"
    bl_label = "Remove location keyframes"
    bl_description = "Removes all recorded location keyframes in selected objects at current frame time"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "location")

class OBJECT_OT_RemoveEulerRotationKeyframes(bpy.types.Operator):
    """RemoveEulerRotationKeyframes"""
    bl_idname = "object.remove_euler_rotation_keyframes"
    bl_label = "Remove euler rotation keyframes"
    bl_description = "Removes all recorded euler rotation keyframes in selected objects at current frame time"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "rotation_euler")

class OBJECT_OT_RemoveQuatRotationKeyframes(bpy.types.Operator):
    """RemoveQuatRotationKeyframes"""
    bl_idname = "object.remove_quat_rotation_keyframes"
    bl_label = "Remove quat rotation keyframes"
    bl_description = "Removes all recorded quat rotation keyframes in selected objects at current frame time"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "rotation_quaternion")

class OBJECT_OT_RemoveScaleKeyframes(bpy.types.Operator):
    """RemoveScaleKeyframes"""
    bl_idname = "object.remove_scale_keyframes"
    bl_label = "Remove scale keyframes"
    bl_description = "Removes all recorded scale keyframes in selected objects at current frame time"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "scale")

class OBJECT_OT_SelectMergeByDistance(bpy.types.Operator):
    """Select vertices that would be merged by distance"""
    bl_idname = "object.select_merge_by_distance"
    bl_label = "Select merge by distance"
    bl_description = "Selects vertices that would be affected by merge by distance operation"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        description="Maximum distance between vertices to consider for merging",
        default=0.0001,
        min=0.0,
        max=1.0,
        precision=6,
        step=0.01,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        return selectMergeByDistanceVerts(self, context, self.threshold)

class OBJECT_OT_CleanUpMaterialsAndImages(bpy.types.Operator):
    """Clean Up Materials And Images"""
    bl_idname = "object.clean_up_materials_and_images"
    bl_label = "Clean up materials and images"
    bl_description = "Cleans up materials and images"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return cleanUpMaterialsAndImages(context)

class OBJECT_OT_RotateFaceVertexIndices(bpy.types.Operator):
    """Rotate selected faces' vertex indices"""
    bl_idname = "object.rotate_face_vertex_indices"
    bl_label = "Rotates selected faces' vertex indices"
    bl_description = "Rotates selected faces' vertex indices"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return rotateFaceVertexIndices(context)

class SCENE_OT_ToggleRenderers(bpy.types.Operator):
    """Toggle Renderers"""
    bl_idname = "scene.toggle_renderers"
    bl_label = "Toggle renderers"
    bl_description = "Toggle renderers (Cycles and Workbench)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if context.scene.render.engine == 'CYCLES':
            context.scene.render.engine = 'BLENDER_WORKBENCH'
        else:
            context.scene.render.engine = 'CYCLES'
        return {'FINISHED'}

class SCENE_OT_PauseRender(bpy.types.Operator):
    """Pause Render"""
    bl_idname = "scene.pause_render"
    bl_label = "Pause render"
    bl_description = "Pause render in viewport"
    bl_options = {'REGISTER'}

    def execute(self, context):
        context.scene.cycles.preview_pause =  not context.scene.cycles.preview_pause
        return {'FINISHED'}

# -----------------------------------------------------------------------------
# Panels

class OBJECT_PT_object_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_object_utilities"
    bl_label = "Object utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_context = 'objectmode'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (context.selected_objects is not None)

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.operator("object.purge_all")
        box.operator("object.hide_all_particles")
        box.operator("object.show_all_particles")

        box = layout.box()
        box.operator("object.diff_object_data")
        box.operator("object.sync_object_properties")
        box.operator("object.copy_object_property_values")
        box.operator("object.copy_object_materials")
        box.operator("object.make_all_properties_overridable")
        box.operator("object.toggle_shadow_catcher")

        box.alert = True
        box.operator("object.remove_empty_vertex_groups")
        box.operator("object.remove_all_modifiers")
        box.operator("object.clean_and_apply_modifiers")
        box.operator("object.update_common_mesh")
        box.alert = False

        box = layout.box()
        box.operator("object.copy_object_transform")
        row = box.row()
        row.enabled = _copied_transform is not None
        row.operator("object.paste_object_transform")

        box = layout.box()
        box.operator("object.copy_modifier_params")
        row = box.row()
        row.enabled = _copied_modifier_data is not None
        row.operator("object.paste_modifier_params")

        box = layout.box()
        box.operator("object.remove_location_keyframes")
        box.operator("object.remove_euler_rotation_keyframes")
        box.operator("object.remove_quat_rotation_keyframes")
        box.operator("object.remove_scale_keyframes")

class OBJECT_PT_misc_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_misc_utilities"
    bl_label = "Misc utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_context = 'objectmode'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        layout.operator("object.clean_up_materials_and_images")

class OBJECT_PT_object_edit_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_object_edit_utilities"
    bl_label = "Object edit utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_context = 'mesh_edit'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True
        # (context.selected_objects is not None)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.operator("object.select_merge_by_distance")

class SCENE_PT_render_utilities(bpy.types.Panel):
    bl_idname = "SCENE_PT_render_utilities"
    bl_label = "Render utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        layout.operator("scene.toggle_renderers")
        layout.operator("scene.pause_render")

# -----------------------------------------------------------------------------
# Sun position calculator

_updating_sun_coords = 0

def compute_sun_position(lat, lon, year, month, day, hour, minute, utc_offset):
    n = datetime(year, month, day).timetuple().tm_yday

    gamma = 2 * math.pi / 365 * (n - 1)

    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2*gamma) + 0.000907 * math.sin(2*gamma)
            - 0.002697 * math.cos(3*gamma) + 0.00148 * math.sin(3*gamma))

    eot = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                    - 0.014615 * math.cos(2*gamma) - 0.04089 * math.sin(2*gamma))

    time_local = hour + minute / 60.0
    time_utc = time_local - utc_offset
    solar_time = time_utc + lon / 15.0 + eot / 60.0
    ha = math.radians(15 * (solar_time - 12))

    lat_rad = math.radians(lat)

    sin_elev = (math.sin(lat_rad) * math.sin(decl) +
                math.cos(lat_rad) * math.cos(decl) * math.cos(ha))
    sin_elev = max(-1, min(1, sin_elev))
    elevation = math.degrees(math.asin(sin_elev))

    if math.cos(math.asin(sin_elev)) > 0.001:
        az_rad = math.atan2(math.sin(ha),
                            math.cos(ha) * math.sin(lat_rad) - math.tan(decl) * math.cos(lat_rad))
        az_south = math.degrees(az_rad) % 360
        azimuth = (az_south + 180) % 360
    else:
        azimuth = 0.0

    return elevation, azimuth


def _sun_auto_calc(props, context):
    if not props.auto_calc:
        return
    try:
        elevation, azimuth = compute_sun_position(
            props.latitude, props.longitude,
            props.year, props.month, props.day,
            props.hour, props.minute, props.utc_offset
        )
        props.elevation = round(elevation, 4)
        props.azimuth = round(azimuth, 4)
    except:
        pass


def _update_lat_dec(self, context):
    global _updating_sun_coords
    if _updating_sun_coords > 0:
        return
    _updating_sun_coords += 1
    try:
        v = abs(self.latitude)
        d = int(v)
        m = int((v - d) * 60)
        s = ((v - d) * 60 - m) * 60
        if self.lat_deg != d:
            self.lat_deg = d
        if self.lat_min != m:
            self.lat_min = m
        if abs(self.lat_sec - s) > 0.0001:
            self.lat_sec = s
        _sun_auto_calc(self, context)
    finally:
        _updating_sun_coords -= 1


def _update_lon_dec(self, context):
    global _updating_sun_coords
    if _updating_sun_coords > 0:
        return
    _updating_sun_coords += 1
    try:
        v = abs(self.longitude)
        d = int(v)
        m = int((v - d) * 60)
        s = ((v - d) * 60 - m) * 60
        if self.lon_deg != d:
            self.lon_deg = d
        if self.lon_min != m:
            self.lon_min = m
        if abs(self.lon_sec - s) > 0.0001:
            self.lon_sec = s
        _sun_auto_calc(self, context)
    finally:
        _updating_sun_coords -= 1


def _update_lat_dms(self, context):
    global _updating_sun_coords
    if _updating_sun_coords > 0:
        return
    _updating_sun_coords += 1
    try:
        v = self.lat_deg + self.lat_min / 60.0 + self.lat_sec / 3600.0
        if self.lat_dir == 'S':
            v = -v
        if abs(self.latitude - v) > 0.000001:
            self.latitude = v
    finally:
        _updating_sun_coords -= 1
    _sun_auto_calc(self, context)


def _update_lon_dms(self, context):
    global _updating_sun_coords
    if _updating_sun_coords > 0:
        return
    _updating_sun_coords += 1
    try:
        v = self.lon_deg + self.lon_min / 60.0 + self.lon_sec / 3600.0
        if self.lon_dir == 'W':
            v = -v
        if abs(self.longitude - v) > 0.000001:
            self.longitude = v
    finally:
        _updating_sun_coords -= 1
    _sun_auto_calc(self, context)


def _sun_date_time_changed(self, context):
    _sun_auto_calc(self, context)


class SunCalculatorProperties(bpy.types.PropertyGroup):
    latitude: bpy.props.FloatProperty(
        name="Latitude",
        description="Latitude in decimal degrees (-90 to 90)",
        default=48.8566,
        min=-90.0, max=90.0,
        update=_update_lat_dec,
    )
    longitude: bpy.props.FloatProperty(
        name="Longitude",
        description="Longitude in decimal degrees (-180 to 180)",
        default=2.3522,
        min=-180.0, max=180.0,
        update=_update_lon_dec,
    )

    lat_deg: bpy.props.IntProperty(
        name="\u00b0", description="Latitude degrees",
        default=48, min=0, max=90,
        update=_update_lat_dms,
    )
    lat_min: bpy.props.IntProperty(
        name="'", description="Latitude minutes",
        default=0, min=0, max=59,
        update=_update_lat_dms,
    )
    lat_sec: bpy.props.FloatProperty(
        name='"', description="Latitude seconds",
        default=0.0, min=0.0, max=59.999,
        update=_update_lat_dms,
    )
    lon_deg: bpy.props.IntProperty(
        name="\u00b0", description="Longitude degrees",
        default=2, min=0, max=180,
        update=_update_lon_dms,
    )
    lon_min: bpy.props.IntProperty(
        name="'", description="Longitude minutes",
        default=0, min=0, max=59,
        update=_update_lon_dms,
    )
    lon_sec: bpy.props.FloatProperty(
        name='"', description="Longitude seconds",
        default=0.0, min=0.0, max=59.999,
        update=_update_lon_dms,
    )

    lat_dir: bpy.props.EnumProperty(
        name="Lat hemisphere",
        items=[('N', "N", "North"), ('S', "S", "South")],
        default='N',
        update=_update_lat_dms,
    )
    lon_dir: bpy.props.EnumProperty(
        name="Lon hemisphere",
        items=[('E', "E", "East"), ('W', "W", "West")],
        default='E',
        update=_update_lon_dms,
    )

    use_dms: bpy.props.BoolProperty(
        name="DMS",
        description="Display coordinates in degrees/minutes/seconds",
        default=False,
    )

    year: bpy.props.IntProperty(
        name="Year", default=2025, min=1, max=3000,
        update=_sun_date_time_changed,
    )
    month: bpy.props.IntProperty(
        name="Month", default=6, min=1, max=12,
        update=_sun_date_time_changed,
    )
    day: bpy.props.IntProperty(
        name="Day", default=21, min=1, max=31,
        update=_sun_date_time_changed,
    )
    hour: bpy.props.IntProperty(
        name="Hour", default=12, min=0, max=23,
        update=_sun_date_time_changed,
    )
    minute: bpy.props.IntProperty(
        name="Min", default=0, min=0, max=59,
        update=_sun_date_time_changed,
    )
    utc_offset: bpy.props.FloatProperty(
        name="UTC+",
        description="UTC offset in hours (e.g. 1 for CET, -5 for EST)",
        default=0, min=-12, max=14,
        update=_sun_date_time_changed,
    )

    azimuth: bpy.props.FloatProperty(
        name="Sun azimuth",
        description="Calculated sun azimuth in degrees (0=North, clockwise)",
        default=0.0,
    )
    elevation: bpy.props.FloatProperty(
        name="Sun elevation",
        description="Calculated sun elevation in degrees",
        default=0.0,
    )
    auto_calc: bpy.props.BoolProperty(
        name="Auto",
        description="Automatically recalculate on input change",
        default=True,
    )


class SCENE_OT_CalculateSunPosition(bpy.types.Operator):
    bl_idname = "scene.calculate_sun_position"
    bl_label = "Calculate"
    bl_description = "Calculate sun azimuth and elevation from coordinates and time"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.sun_calculator
        try:
            elevation, azimuth = compute_sun_position(
                props.latitude, props.longitude,
                props.year, props.month, props.day,
                props.hour, props.minute, props.utc_offset
            )
            props.elevation = round(elevation, 4)
            props.azimuth = round(azimuth, 4)
            self.report({'INFO'}, f"Azimuth: {azimuth:.2f}°  Elevation: {elevation:.2f}°")
        except Exception as e:
            self.report({'ERROR'}, f"Invalid date/time: {str(e)}")
            return {'CANCELLED'}
        return {'FINISHED'}


class SCENE_OT_ApplySunToSky(bpy.types.Operator):
    bl_idname = "scene.apply_sun_to_sky"
    bl_label = "Use \u2192 Sky Texture"
    bl_description = "Transfer calculated azimuth and elevation to the Sky Texture in the World material"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        world = context.scene.world
        if world is None or not world.use_nodes or world.node_tree is None:
            return False
        for node in world.node_tree.nodes:
            if node.type in ('SKY', 'TEX_SKY'):
                return True
        return False

    def execute(self, context):
        props = context.scene.sun_calculator
        world = context.scene.world
        for node in world.node_tree.nodes:
            if node.type in ('SKY', 'TEX_SKY'):
                node.sun_elevation = math.radians(props.elevation)
                node.sun_rotation = math.radians(props.azimuth)
                self.report({'INFO'}, f"Sky texture updated: elev={props.elevation:.2f}°  azim={props.azimuth:.2f}°")
                return {'FINISHED'}
        self.report({'WARNING'}, "No Sky Texture node found in world")
        return {'CANCELLED'}


# -----------------------------------------------------------------------------
# Panels

class SCENE_PT_general_utilities(bpy.types.Panel):
    bl_idname = "SCENE_PT_general_utilities"
    bl_label = "General utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        props = context.scene.sun_calculator

        box = layout.box()
        box.label(text="Sun position", icon='LIGHT_SUN')

        row = box.row()
        row.prop(props, "use_dms", text="DMS")
        if props.use_dms:
            row = box.row(align=True)
            row.prop(props, "lat_dir", text="")
            row.prop(props, "lat_deg")
            row.prop(props, "lat_min")
            row.prop(props, "lat_sec")
            row = box.row(align=True)
            row.prop(props, "lon_dir", text="")
            row.prop(props, "lon_deg")
            row.prop(props, "lon_min")
            row.prop(props, "lon_sec")
        else:
            row = box.row(align=True)
            row.prop(props, "latitude")
            row = box.row(align=True)
            row.prop(props, "longitude")

        box.separator()

        row = box.row(align=True)
        row.prop(props, "year")
        row.prop(props, "month")
        row.prop(props, "day")

        row = box.row(align=True)
        row.prop(props, "hour")
        row.prop(props, "minute")
        row.prop(props, "utc_offset")

        box.separator()

        row = box.row()
        row.operator("scene.calculate_sun_position")
        row.prop(props, "auto_calc")

        col = box.column()
        col.prop(props, "azimuth")
        col.prop(props, "elevation")

        box.separator()

        row = box.row()
        row.operator("scene.apply_sun_to_sky")


# -----------------------------------------------------------------------------
# Registering

addon_keymaps = []

def register():
    bpy.utils.register_class(OBJECT_OT_PurgeAll)
    bpy.utils.register_class(OBJECT_OT_HideAllParticles)
    bpy.utils.register_class(OBJECT_OT_ShowAllParticles)
    bpy.utils.register_class(OBJECT_OT_DiffObjectData)
    bpy.utils.register_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.register_class(OBJECT_OT_CopyObjectPropertyValues)
    bpy.utils.register_class(OBJECT_OT_CopyObjectMaterials)
    bpy.utils.register_class(OBJECT_OT_MakeAllPropertiesOverridable)
    bpy.utils.register_class(OBJECT_OT_CleanAndApplyModifiers)
    bpy.utils.register_class(OBJECT_OT_ToggleShadowCatcher)
    bpy.utils.register_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.register_class(OBJECT_OT_RemoveAllModifiers)
    bpy.utils.register_class(OBJECT_OT_UpdateCommonMesh)

    bpy.utils.register_class(OBJECT_OT_CopyObjectTransform)
    bpy.utils.register_class(OBJECT_OT_PasteObjectTransform)
    bpy.utils.register_class(OBJECT_OT_CopyModifierParams)
    bpy.utils.register_class(OBJECT_OT_PasteModifierParams)
    bpy.utils.register_class(OBJECT_OT_RemoveLocationKeyframes)
    bpy.utils.register_class(OBJECT_OT_RemoveEulerRotationKeyframes)
    bpy.utils.register_class(OBJECT_OT_RemoveQuatRotationKeyframes)
    bpy.utils.register_class(OBJECT_OT_RemoveScaleKeyframes)

    bpy.utils.register_class(OBJECT_OT_SelectMergeByDistance)
    bpy.utils.register_class(OBJECT_OT_CleanUpMaterialsAndImages)
#    bpy.utils.register_class(OBJECT_OT_RotateFaceVertexIndices)
    bpy.utils.register_class(SCENE_OT_ToggleRenderers)
    bpy.utils.register_class(SCENE_OT_PauseRender)

    bpy.utils.register_class(SunCalculatorProperties)
    bpy.types.Scene.sun_calculator = bpy.props.PointerProperty(type=SunCalculatorProperties)
    bpy.utils.register_class(SCENE_OT_CalculateSunPosition)
    bpy.utils.register_class(SCENE_OT_ApplySunToSky)

    bpy.utils.register_class(OBJECT_PT_object_utilities)
    bpy.utils.register_class(OBJECT_PT_misc_utilities)
    bpy.utils.register_class(OBJECT_PT_object_edit_utilities)
    bpy.utils.register_class(SCENE_PT_render_utilities)
    bpy.utils.register_class(SCENE_PT_general_utilities)

    # handle the keymap
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(SCENE_OT_ToggleRenderers.bl_idname, type='R', value='PRESS', alt=True, shift=True)
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    bpy.utils.unregister_class(OBJECT_OT_PurgeAll)
    bpy.utils.unregister_class(OBJECT_OT_HideAllParticles)
    bpy.utils.unregister_class(OBJECT_OT_ShowAllParticles)
    bpy.utils.unregister_class(OBJECT_OT_DiffObjectData)
    bpy.utils.unregister_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.unregister_class(OBJECT_OT_CopyObjectPropertyValues)
    bpy.utils.unregister_class(OBJECT_OT_CopyObjectMaterials)
    bpy.utils.unregister_class(OBJECT_OT_MakeAllPropertiesOverridable)
    bpy.utils.unregister_class(OBJECT_OT_CleanAndApplyModifiers)
    bpy.utils.unregister_class(OBJECT_OT_ToggleShadowCatcher)
    bpy.utils.unregister_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.unregister_class(OBJECT_OT_RemoveAllModifiers)
    bpy.utils.unregister_class(OBJECT_OT_UpdateCommonMesh)

    bpy.utils.unregister_class(OBJECT_OT_CopyObjectTransform)
    bpy.utils.unregister_class(OBJECT_OT_PasteObjectTransform)
    bpy.utils.unregister_class(OBJECT_OT_CopyModifierParams)
    bpy.utils.unregister_class(OBJECT_OT_PasteModifierParams)
    bpy.utils.unregister_class(OBJECT_OT_RemoveLocationKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_RemoveEulerRotationKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_RemoveQuatRotationKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_RemoveScaleKeyframes)

    bpy.utils.unregister_class(OBJECT_OT_SelectMergeByDistance)
    bpy.utils.unregister_class(OBJECT_OT_CleanUpMaterialsAndImages)
#    bpy.utils.unregister_class(OBJECT_OT_RotateFaceVertexIndices)
    bpy.utils.unregister_class(SCENE_OT_ToggleRenderers)
    bpy.utils.unregister_class(SCENE_OT_PauseRender)

    bpy.utils.unregister_class(SCENE_OT_CalculateSunPosition)
    bpy.utils.unregister_class(SCENE_OT_ApplySunToSky)
    del bpy.types.Scene.sun_calculator
    bpy.utils.unregister_class(SunCalculatorProperties)

    bpy.utils.unregister_class(OBJECT_PT_object_utilities)
    bpy.utils.unregister_class(OBJECT_PT_misc_utilities)
    bpy.utils.unregister_class(OBJECT_PT_object_edit_utilities)
    bpy.utils.unregister_class(SCENE_PT_render_utilities)
    bpy.utils.unregister_class(SCENE_PT_general_utilities)

if __name__ == "__main__":
    register()
