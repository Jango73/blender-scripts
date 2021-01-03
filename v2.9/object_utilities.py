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
        layout.operator("object.sync_object_properties")
        layout.operator("object.remove_empty_vertex_groups")

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
    bpy.utils.register_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.register_class(OBJECT_OT_RemoveEmptyVertexGroups)
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

    bpy.utils.unregister_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.unregister_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.unregister_class(OBJECT_OT_CleanUpMaterialsAndImages)
    bpy.utils.unregister_class(SCENE_OT_ToggleRenderers)
    bpy.utils.unregister_class(SCENE_OT_PauseRender)
    bpy.utils.unregister_class(OBJECT_PT_object_utilities)
    bpy.utils.unregister_class(OBJECT_PT_misc_utilities)
    bpy.utils.unregister_class(SCENE_PT_render_utilities)

if __name__ == "__main__":
    register()
