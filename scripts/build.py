#!/usr/bin/env python3
"""Render site/index.html from scripts/template.html and data/days.json."""
import os
here = os.path.dirname(os.path.abspath(__file__))
data = open(os.path.join(here, "..", "data", "days.json"), encoding="utf8").read().replace("</", "<\\/")
tpl = open(os.path.join(here, "template.html"), encoding="utf8").read()
os.makedirs(os.path.join(here, "..", "site"), exist_ok=True)
import datetime
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=4))).strftime("%Y-%m-%d %H:%M")
open(os.path.join(here, "..", "site", "index.html"), "w", encoding="utf8").write(tpl.replace("__DATA__", data).replace("__UPDATED__", now))
print("site/index.html written")
