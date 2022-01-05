# blender-scripts
Blender utility scripts for various versions.

## Scripts for Blender 3.0, in /v3.0

### armature_utilities.py
* Refresh the constraints and properties of an armature proxy that links to another blender file. (Does not work with NLA, must fix)
* Copy all bone constraints from one armature to another, using bone names for matching.

### object_utilities.py
* View the difference between two objects' data (Custom properties, vertex groups, vertex colors, modifiers)
* Copy all custom property values from one object to another (only for properties existing in both objects)
* Make all custom properties, in selected object, "library overridable"
* Remove, from selected objects, all vertex groups that contain only zero values (below 0.01).
* Remove all modifiers of selected objects
* Remove location keyframes of selected objects (and its bones if armature) for the current frame time
* Remove rotation keyframes of selected objects (and its bones if armature) for the current frame time
* Remove scale keyframes of selected objects (and its bones if armature) for the current frame time

## Scripts for Blender 2.9, in /v2.9

### armature_utilities.py
* Refresh the constraints and properties of an armature proxy that links to another blender file. (Does not work with NLA, must fix)
* Copy all bone constraints from one armature to another, using bone names for matching.

### object_utilities.py
* View the difference between two objects' data (Custom properties, vertex groups, vertex colors, modifiers)
* Synchronize two objects' custom properties (removes properties existing only in the target object)
* Remove, from selected objects, all vertex groups that contain only zero values (below 0.01).
* Remove all modifiers of selected objects
* Remove location keyframes of selected objects (and its bones if armature) for the current frame time
* Remove rotation keyframes of selected objects (and its bones if armature) for the current frame time
* Remove scale keyframes of selected objects (and its bones if armature) for the current frame time

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
