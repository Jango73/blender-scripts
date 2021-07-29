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
    "version": (1, 0),
    "blender": (2, 80, 0),
    "description": "Operations on objects",
    "category": "Object",
}

import bpy
import re
import copy

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

    if "_RNA_UI" in source and "_RNA_UI" in target:
        targetString = printToString(targetString, "[ Custom properties ]")

        props1 = source["_RNA_UI"]
        props2 = target["_RNA_UI"]

        for p in props1.keys():
            lines1.append(p.strip())
        for p in props2.keys():
            lines2.append(p.strip())

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
    
    return ''

# -----------------------------------------------------------------------------

def syncObjectProperties(self, context):
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

    props = source["_RNA_UI"]

    for p in props.keys():
        if not p.startswith("_"):
            if p not in target.keys():
                target[p] = source[p]

    self.report({'INFO'}, "Synced " + target.name + " properties with " + source.name)

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeEmptyVertexGroups(context):
    # get active object
    ob = context.active_object

    if ob is None:
        return {'CANCELLED'}

    ob.update_from_editmode()

    vgroup_used = {i: False for i, k in enumerate(ob.vertex_groups)}
    vgroup_names = {i: k.name for i, k in enumerate(ob.vertex_groups)}
    vgroup_name_list = list(vgroup_names.values())

    for v in ob.data.vertices:
        for g in v.groups:

            mirrored_name = getMirroredName(vgroup_names[g.group])

            if mirrored_name in vgroup_name_list:
                vgroup_used[g.group] = vgroup_used[vgroup_name_list.index(mirrored_name)]
            else:
                if g.weight > 0.01:
                    vgroup_used[g.group] = True

    for i, used in sorted(vgroup_used.items(), reverse=True):
        if not used:
            ob.vertex_groups.remove(ob.vertex_groups[i])

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeAllModifiers(context):
    # get active object
    object = context.active_object

    if object is None:
        return {'CANCELLED'}

    # remove all modifiers
    object.modifiers.clear()

    return {'FINISHED'}

# -----------------------------------------------------------------------------

def removeKeyframesByChannel(self, context, channel):
    # get active object
    object = context.active_object

    if object is None:
        return {'CANCELLED'}

    if object.animation_data:
        action = object.animation_data.action
        if action:
            for fc in action.fcurves:
                if fc.data_path.endswith(channel):
                    try:
                        object.keyframe_delete(fc.data_path)
                    except TypeError:
                        print(fc.data_path + " channel does not exist. Ignoring.")

    self.report({'INFO'}, "Removed " + channel + " type keyframes from active armature (" + object.name + ")")
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
# Operators

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

class OBJECT_OT_RemoveEmptyVertexGroups(bpy.types.Operator):
    """Remove Empty Vertex Groups"""
    bl_idname = "object.remove_empty_vertex_groups"
    bl_label = "Remove empty vertex groups"
    bl_description = "Removes empty vertex groups"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeEmptyVertexGroups(context)

class OBJECT_OT_RemoveAllModifiers(bpy.types.Operator):
    """Remove All Modifiers"""
    bl_idname = "object.remove_all_modifiers"
    bl_label = "Remove all modifiers"
    bl_description = "Removes all modifiers"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeAllModifiers(context)

class OBJECT_OT_RemoveLocationKeyframes(bpy.types.Operator):
    """RemoveLocationKeyframes"""
    bl_idname = "object.remove_location_keyframes"
    bl_label = "Remove location keyframes"
    bl_description = "Removes all location keyframes in active object for current frame"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "location")

class OBJECT_OT_RemoveRotationKeyframes(bpy.types.Operator):
    """RemoveRotationKeyframes"""
    bl_idname = "object.remove_rotation_keyframes"
    bl_label = "Remove rotation keyframes"
    bl_description = "Removes all rotation keyframes in active object for current frame"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "rotation_quaternion")

class OBJECT_OT_RemoveScaleKeyframes(bpy.types.Operator):
    """RemoveScaleKeyframes"""
    bl_idname = "object.remove_scale_keyframes"
    bl_label = "Remove scale keyframes"
    bl_description = "Removes all scale keyframes in active object for current frame"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeKeyframesByChannel(self, context, "scale")

class OBJECT_OT_CleanUpMaterialsAndImages(bpy.types.Operator):
    """Clean Up Materials And Images"""
    bl_idname = "object.clean_up_materials_and_images"
    bl_label = "Clean up materials and images"
    bl_description = "Cleans up materials and images"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return cleanUpMaterialsAndImages(context)

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

    @classmethod
    def poll(cls, context):
        return (context.object is not None)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.operator("object.diff_object_data")
        box.operator("object.sync_object_properties")
        box.operator("object.remove_empty_vertex_groups")
        box.operator("object.remove_all_modifiers")
        box = layout.box()
        box.operator("object.remove_location_keyframes")
        box.operator("object.remove_rotation_keyframes")
        box.operator("object.remove_scale_keyframes")

class OBJECT_PT_misc_utilities(bpy.types.Panel):
    bl_idname = "OBJECT_PT_misc_utilities"
    bl_label = "Misc utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_context = 'objectmode'

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        layout.operator("object.clean_up_materials_and_images")

class SCENE_PT_render_utilities(bpy.types.Panel):
    bl_idname = "SCENE_PT_render_utilities"
    bl_label = "Render utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        layout.operator("scene.toggle_renderers")
        layout.operator("scene.pause_render")

# -----------------------------------------------------------------------------
# Registering

addon_keymaps = []

def register():
    bpy.utils.register_class(OBJECT_OT_DiffObjectData)
    bpy.utils.register_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.register_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.register_class(OBJECT_OT_RemoveAllModifiers)
    bpy.utils.register_class(OBJECT_OT_RemoveLocationKeyframes)
    bpy.utils.register_class(OBJECT_OT_RemoveRotationKeyframes)
    bpy.utils.register_class(OBJECT_OT_RemoveScaleKeyframes)
    bpy.utils.register_class(OBJECT_OT_CleanUpMaterialsAndImages)
    bpy.utils.register_class(SCENE_OT_ToggleRenderers)
    bpy.utils.register_class(SCENE_OT_PauseRender)
    bpy.utils.register_class(OBJECT_PT_object_utilities)
    bpy.utils.register_class(OBJECT_PT_misc_utilities)
    bpy.utils.register_class(SCENE_PT_render_utilities)

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

    bpy.utils.unregister_class(OBJECT_OT_DiffObjectData)
    bpy.utils.unregister_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.unregister_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.unregister_class(OBJECT_OT_RemoveAllModifiers)
    bpy.utils.unregister_class(OBJECT_OT_RemoveLocationKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_RemoveRotationKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_RemoveScaleKeyframes)
    bpy.utils.unregister_class(OBJECT_OT_CleanUpMaterialsAndImages)
    bpy.utils.unregister_class(SCENE_OT_ToggleRenderers)
    bpy.utils.unregister_class(SCENE_OT_PauseRender)
    bpy.utils.unregister_class(OBJECT_PT_object_utilities)
    bpy.utils.unregister_class(OBJECT_PT_misc_utilities)
    bpy.utils.unregister_class(SCENE_PT_render_utilities)

if __name__ == "__main__":
    register()
