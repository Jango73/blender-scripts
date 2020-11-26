# --------------------------------------------------------------------------
# Clean-up Utilities (author Jango73)
# - Remove unused materials and images
# --------------------------------------------------------------------------
# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****
# --------------------------------------------------------------------------

bl_info = {
    "name": "Clean-up utilities",
    "author": "Jango73",
    "version": (1, 0),
    "blender": (2, 57, 0),
    "location": "Tools > Clean-up utilities",
    "description": "Provides utilities for scene clean-up",
    "warning": "",
    "wiki_url": ""
                "",
    "category": "3D View",
}

"""
Usage:

Launch from "Tools -> Clean-up utilities"


Additional links:
    e-mail: therealjango73 {at} gmail {dot} com
"""

import bpy
import bmesh
from bpy.props import IntProperty
from bpy.types import Operator, Panel

def clean_up_images(self, context):
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

class CleanUpImages(bpy.types.Operator):
    """Removes unused images in the scene"""
    bl_idname = 'mesh.clean_up_images'
    bl_label = 'Clean-up images'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return clean_up_images(self, context)

class c_clean_up_utilities(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = 'Tools'
    bl_label = "Clean-up utilities"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator(CleanUpImages.bl_idname, text="Clean-up images")

def register():
    bpy.utils.register_module(__name__)

def unregister():
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
