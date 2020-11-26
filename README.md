# blender-scripts
Blender utility scripts for various versions.

## Scripts for Blender 2.9

### RefreshArmatureProxy.py 
* Implements missing functionality with armature proxies: refresh the constraints and properties when they have been modified in the source file.
  * Does this by creating a new proxy and copying the animation every nth frame (parameters set in the script).

### CopyArmatureConstraints.py
* Copies all bone constraints from one armature to another, using bone names for matching.

## Scripts for Blender 2.7x

### mesh_modifiers_utilities.py
This scripts enables the following operations:
* Copy the modifiers from an object to another
* Remove all modifiers from an object
* Toggle on/off all modifiers of an object in the viewport
* Toggle on/off specified modifiers of an object in the viewport
  * Modifer names must be listed in the object's property named "Modifiers"

### lichtwerk_MeshTransfer
This script is copyright Philipp Oeser.

* Enables transfer of vertex groups from one mesh to another
