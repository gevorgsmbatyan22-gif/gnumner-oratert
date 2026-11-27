#!/usr/bin/env python3
"""Render site/index.html from scripts/template.html and data/days.json."""
import os
here = os.path.dirname(os.path.abspath(__file__))
data = open(os.path.join(here, "..", "data", "days.json"), encoding="utf8").read().replace("</", "<\\/")
tpl = open(os.path.join(here, "template.html"), encoding="utf8").read()
os.makedirs(os.path.join(here, "..", "site"), exist_ok=True)
open(os.path.join(here, "..", "site", "index.html"), "w", encoding="utf8").write(tpl.replace("__DATA__", data))
print("site/index.html written")
