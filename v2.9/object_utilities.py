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

def syncObjectProperties(context):
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

    for v in ob.data.vertices:
        for g in v.groups:
            if g.weight > 0.01:
                vgroup_used[g.group] = True
                vgroup_name = vgroup_names[g.group]
                armatch = re.search('((.R|.L)(.(\d){1,}){0,1})(?!.)', vgroup_name)
                if armatch != None:
                    tag = armatch.group()
                    mirror_tag =  tag.replace(".R", ".L") if armatch.group(2) == ".R" else tag.replace(".L", ".R") 
                    mirror_vgname = vgroup_name.replace(tag, mirror_tag)
                    for i, name in sorted(vgroup_names.items(), reverse=True):
                        if mirror_vgname == name:
                            vgroup_used[i] = True
                            break
    for i, used in sorted(vgroup_used.items(), reverse=True):
        if not used:
            ob.vertex_groups.remove(ob.vertex_groups[i])

    return {'FINISHED'}

# -----------------------------------------------------------------------------

class OBJECT_OT_SyncObjectProperties(bpy.types.Operator):
    """Sync Object Properties"""
    bl_idname = "object.sync_object_properties"
    bl_label = "Sync object properties"
    bl_description = "Synchronizes the properties of an object with another"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return syncObjectProperties(context)

class OBJECT_OT_RemoveEmptyVertexGroups(bpy.types.Operator):
    """Remove Empty Vertex Groups"""
    bl_idname = "object.remove_empty_vertex_groups"
    bl_label = "Remove empty vertex groups"
    bl_description = "Removes empty vertex groups"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return removeEmptyVertexGroups(context)

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

def register():
    bpy.utils.register_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.register_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.register_class(OBJECT_PT_object_utilities)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_SyncObjectProperties)
    bpy.utils.unregister_class(OBJECT_OT_RemoveEmptyVertexGroups)
    bpy.utils.unregister_class(OBJECT_PT_object_utilities)

if __name__ == "__main__":
    register()
