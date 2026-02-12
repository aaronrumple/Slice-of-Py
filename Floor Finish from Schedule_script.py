# -*- coding: utf-8 -*-
# Aaron Rumple, AIA

import sys
from pyrevit import revit, DB, script, forms
from Autodesk.Revit.DB import *
from System.Collections.Generic import List

doc = revit.doc
output = script.get_output()

ROOM_FINISH_PARAM_NAME = "Floor Finish"
LAYER_THICKNESS_FT = 0.25 / 12.0  # 1/4"

def get_or_create_material(name):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name:
            return m
    return doc.GetElement(Material.Create(doc, name))

def get_or_create_floor_type(type_name, material):
    for ft in FilteredElementCollector(doc).OfClass(FloorType):
        p = ft.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.AsString() == type_name:
            return ft

    arch_types = []

    for ft in FilteredElementCollector(doc).OfClass(FloorType):
        # Exclude foundation slabs by family name
        fam_name = ft.FamilyName or ""
        if "Foundation" in fam_name:
            continue
        arch_types.append(ft)

    if not arch_types:
        raise Exception("No architectural (non-structural) floor types found in project.")

    base_type = arch_types[0]

    new_type = base_type.Duplicate(type_name)

    p_struct_new = new_type.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
    if p_struct_new and not p_struct_new.IsReadOnly:
        p_struct_new.Set(0)

    cs = new_type.GetCompoundStructure()
    if not cs or cs.LayerCount < 1:
        raise Exception("Invalid compound structure in duplicated floor type.")

    cs.SetLayerWidth(0, LAYER_THICKNESS_FT)
    cs.SetMaterialId(0, material.Id)
    new_type.SetCompoundStructure(cs)

    name_param = new_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    if name_param and not name_param.IsReadOnly:
        name_param.Set(type_name)

    return new_type

floors_by_level_phase = {}

all_floors = (
    FilteredElementCollector(doc)
    .OfClass(Floor)
    .WhereElementIsNotElementType()
)

for f in all_floors:

    level_id = f.LevelId.IntegerValue

    phase_param = f.get_Parameter(BuiltInParameter.PHASE_CREATED)
    if not phase_param:
        continue

    phase_id = phase_param.AsElementId().IntegerValue

    key = (level_id, phase_id)

    if key not in floors_by_level_phase:
        floors_by_level_phase[key] = []

    floors_by_level_phase[key].append(f)

def floor_exists_in_room(room):

    level_id = room.LevelId.IntegerValue

    phase_param = room.get_Parameter(BuiltInParameter.ROOM_PHASE)
    if not phase_param:
        return False

    phase_id = phase_param.AsElementId().IntegerValue

    key = (level_id, phase_id)

    if key not in floors_by_level_phase:
        return False

    if not room.Location:
        return False

    test_pt = room.Location.Point

    for floor in floors_by_level_phase[key]:

        bbox = floor.get_BoundingBox(None)
        if not bbox:
            continue

        if (bbox.Min.X <= test_pt.X <= bbox.Max.X and
            bbox.Min.Y <= test_pt.Y <= bbox.Max.Y):
            return True

    return False

rooms = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Rooms)
    .WhereElementIsNotElementType()
)

t = Transaction(doc, "Create Finish Floors (Phase Aware)")
t.Start()

created = 0
skipped = 0

with forms.ProgressBar(title="Creating Finish Floors", cancellable=True) as pb:

    for i, room in enumerate(rooms):

        if pb.cancelled:
            break

        pb.update_progress(i + 1, len(rooms))

        if room.Area <= 0:
            continue

        finish_param = room.LookupParameter(ROOM_FINISH_PARAM_NAME)
        if not finish_param:
            continue

        finish_name = finish_param.AsString()
        if not finish_name:
            continue

        finish_name = finish_name.strip()
        if not finish_name:
            continue

        # Skip if floor already exists
        if floor_exists_in_room(room):
            skipped += 1
            continue

        mat = get_or_create_material(finish_name)
        floor_type = get_or_create_floor_type(finish_name, mat)

        # 🔹 Finish boundary (includes linked room bounding walls)
        opts = SpatialElementBoundaryOptions()
        opts.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish

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

        floor = Floor.Create(
            doc,
            curve_loops,
            floor_type.Id,
            level.Id
        )

        if not floor:
            continue

        room_phase_param = room.get_Parameter(BuiltInParameter.ROOM_PHASE)
        if room_phase_param:
            room_phase_id = room_phase_param.AsElementId()

            floor_phase_param = floor.get_Parameter(BuiltInParameter.PHASE_CREATED)
            if floor_phase_param and not floor_phase_param.IsReadOnly:
                floor_phase_param.Set(room_phase_id)

        offset_param = floor.get_Parameter(
            BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM
        )
        if offset_param and not offset_param.IsReadOnly:
            offset_param.Set(-LAYER_THICKNESS_FT)

        # Write Room Number to Mark
        mark_param = floor.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if mark_param and not mark_param.IsReadOnly:
            mark_param.Set(room.Number)

        key = (
            room.LevelId.IntegerValue,
            room_phase_id.IntegerValue
        )

        if key not in floors_by_level_phase:
            floors_by_level_phase[key] = []

        floors_by_level_phase[key].append(floor)

        created += 1

t.Commit()

output.print_md("### ✅ Finished")
output.print_md("Created: **{}** floors".format(created))
output.print_md("Skipped (existing detected): **{}** rooms".format(skipped))
