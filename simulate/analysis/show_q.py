#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys

ids = sys.argv[1:]
with open("simulate/simulation_results.json") as f:
    data = json.load(f)
for r in data["results"]:
    if r["id"] in ids:
        print("=" * 80)
        print("ID:", r["id"])
        print("Q:", r["question"])
        print("CORRECT:", r["correct"])
        print("REF:", r["ref"])
        print("ARTICLE_TITLE:", r.get("article_title"))
