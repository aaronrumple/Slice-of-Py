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

    for ft in floor_types:
        p = ft.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.AsString() == type_name:
            return ft

    base_type = floor_types[0]
    new_type_id = base_type.Duplicate(type_name)
    new_type = doc.GetElement(new_type_id.Id)

    name_param = new_type_id.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    if name_param and not name_param.IsReadOnly:
        name_param.Set(type_name)

    cs = new_type.GetCompoundStructure()
    if cs is None:
        raise Exception("Base floor type has no compound structure.")

    layer_count = cs.LayerCount
    if layer_count < 1:
        raise Exception("Base floor type has no layers.")

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
