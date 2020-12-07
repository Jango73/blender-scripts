# blender-scripts
Blender utility scripts for various versions.

## Scripts for Blender 2.9, in /v2.9

### armature_utilities.py
* Refresh the constraints and properties of an armature proxy that links to another blender file.
* Copy all bone constraints from one armature to another, using bone names for matching.

### object_utilities.py
* Synchronize two objects' custom properties
* Remove, from an object, all vertex groups that contain only zero values (below 0.01).

## Scripts for Blender 2.6, in /v2.6

### lichtwerk_MeshTransfer
This script is copyright Philipp Oeser.
Stored here for convenience.

* Enables transfer of vertex groups from one mesh to another

## Scripts for Blender 2.5, in /v2.5

### clean_up_utilities.py
* Removes all unused materials and images.

### mesh_modifiers_utilities.py
This scripts enables the following operations:
* Copy the modifiers from an object to another
* Remove all modifiers from an object
* Toggle on/off all modifiers of an object in the viewport
* Toggle on/off specified modifiers of an object in the viewport
  * Modifer names must be listed in the object's property named "Modifiers"
