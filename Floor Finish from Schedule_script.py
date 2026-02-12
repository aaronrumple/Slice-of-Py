# -*- coding: utf-8 -*-

from pyrevit import revit, DB, script

from Autodesk.Revit.DB import *

from System.Collections.Generic import List



doc = revit.doc



ROOM_FINISH_PARAM_NAME = "Floor Finish"

LAYER_THICKNESS_FT = 0.25 / 12.0  # 1/4" in feet



output = script.get_output()



def get_or_create_material(mat_name):

    mats = FilteredElementCollector(doc).OfClass(Material).ToElements()

    for m in mats:

        if m.Name == mat_name:

            return m



    mat_id = Material.Create(doc, mat_name)

    return doc.GetElement(mat_id)



def get_or_create_floor_type(type_name, material):

    floor_types = list(FilteredElementCollector(doc).OfClass(FloorType).ToElements())

    if not floor_types:

        raise Exception("No floor types found in project.")



    # Find by element name parameter (safer than ft.Name)

    for ft in floor_types:

        p = ft.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)

        if p and p.AsString() == type_name:

            return ft



    base_type = floor_types[0]

    new_type_id = base_type.Duplicate(type_name)

    new_type = doc.GetElement(new_type_id.Id)



    # Ensure name is set correctly

    name_param = new_type_id.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)

    if name_param and not name_param.IsReadOnly:

        name_param.Set(type_name)



    cs = new_type.GetCompoundStructure()

    if cs is None:

        raise Exception("Base floor type has no compound structure.")



    layer_count = cs.LayerCount

    if layer_count < 1:

        raise Exception("Base floor type has no layers.")



    # Modify first layer safely (NO SetLayers call)

    cs.SetLayerWidth(0, LAYER_THICKNESS_FT)

    cs.SetMaterialId(0, material.Id)



    new_type.SetCompoundStructure(cs)



    return new_type



rooms = FilteredElementCollector(doc)\

    .OfCategory(BuiltInCategory.OST_Rooms)\

    .WhereElementIsNotElementType()\

    .ToElements()



t = Transaction(doc, "Create Floors from Rooms")

t.Start()



created_count = 0



for room in rooms:

    if room.Area <= 0:

        continue



    finish_param = room.LookupParameter(ROOM_FINISH_PARAM_NAME)

    if not finish_param or not finish_param.AsString():

        continue



    finish_name = finish_param.AsString().strip()

    if not finish_name:

        continue



    mat = get_or_create_material(finish_name)

    floor_type = get_or_create_floor_type(finish_name, mat)



    opts = SpatialElementBoundaryOptions()

    boundaries = room.GetBoundarySegments(opts)

    if not boundaries:

        continue



    curve_loops = List[CurveLoop]()

    for loop in boundaries:

        cl = CurveLoop()

        for seg in loop:

            cl.Append(seg.GetCurve())

        curve_loops.Add(cl)



    level = doc.GetElement(room.LevelId)



    floor = Floor.Create(doc, curve_loops, floor_type.Id, level.Id)

    if not floor:

        continue



    # Set floor offset = 1/4"

    offset_param = floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)

    if offset_param and not offset_param.IsReadOnly:

        offset_param.Set(LAYER_THICKNESS_FT)



    # Write Room Number to Floor Mark (built-in)

    mark_param = floor.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)

    if mark_param and not mark_param.IsReadOnly:

        mark_param.Set(room.Number)



    created_count += 1



t.Commit()



output.print_md("### ✅ Done")

output.print_md("Created **{}** floors from rooms.".format(created_count))
