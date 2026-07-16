#!/usr/bin/env python3
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "admin"))
import base_creator


class BaseCreatorTests(unittest.TestCase):
    def test_export_is_portable_and_preserves_exact_transforms(self):
        calls=[]
        def query(sql,args=()):
            calls.append((sql,args))
            if "building_instances where" in sql:
                return [{"instance_id":1,"building_type":"Foundation","transform":[10,20,30,0,0,0,1],"building_flags":1,"health":5000,"owner_entity_id":-99}]
            return [{"id":7,"building_type":"Cistern","is_hologram":False,"transform":{"location":{"x":30,"y":40,"z":50},"rotation":{"x":0,"y":0,"z":1,"w":0}},"map":"HaggaBasin","partition_id":1,"dimension_index":0}]
        archive=base_creator.export_live_base(query,123)
        self.assertEqual(archive["format"],"dash-base/1")
        self.assertEqual(archive["pieceCount"],1)
        self.assertEqual(archive["placeableCount"],1)
        self.assertEqual(archive["pieces"][0]["transform"],[10,20,30,0,0,0,1])
        self.assertEqual(archive["pieces"][0]["relative"][:3],[-10,-10,-10])
        self.assertFalse(archive["gameRestoreSupported"])
        self.assertEqual(len(archive["sha256"]),64)

    def test_invalid_transform_is_rejected(self):
        def query(sql,args=()):
            return [{"instance_id":1,"building_type":"Bad","transform":[1,2],"owner_entity_id":1}] if "building_instances where" in sql else []
        with self.assertRaises(ValueError): base_creator.export_live_base(query,1)

    def test_unowned_world_building_exports_without_placeables(self):
        def query(sql,args=()):
            return [{"instance_id":1,"building_type":"World","transform":[1,2,3,0,0,0,1],"building_flags":0,"health":1,"owner_entity_id":None}]
        archive=base_creator.export_live_base(query,2)
        self.assertIsNone(archive["source"]["ownerEntityId"])
        self.assertEqual(archive["placeableCount"],0)

    def test_gallery_publish_list_rate_and_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"gallery"/"gallery.sqlite3"
            gallery=base_creator.Gallery(path,os.getuid(),os.getgid()).initialize()
            archive={"format":"dash-base/1","pieces":[{"buildingType":"Foundation","relative":[0,0,0,0,0,0,1]}],"placeables":[]}
            item=gallery.publish("Test Base","desc","alice",archive,"public")
            self.assertEqual(gallery.list()[0]["name"],"Test Base")
            rated=gallery.rate(item["id"],"bob",5)
            self.assertEqual(rated["rating_average"],5)
            self.assertEqual(rated["rating_count"],1)
            updated=gallery.publish("Test Base 2","new","alice",archive,"unlisted",item["id"])
            self.assertEqual(updated["name"],"Test Base 2")
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_gallery_validation_bounds_and_visibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            gallery=base_creator.Gallery(pathlib.Path(tmp)/"g.sqlite3").initialize()
            with self.assertRaises(ValueError): gallery.publish("x","","a",{"format":"bad"})
            with self.assertRaises(ValueError): gallery.publish("x","","a",{"format":"dash-base/1","pieces":[],"placeables":[]},"secret")
            with self.assertRaises(ValueError): gallery.rate("missing","a",6)


if __name__ == "__main__": unittest.main()
