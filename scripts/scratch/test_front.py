#!/usr/bin/env python3
import copy
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def w(tag: str) -> str: return f"{{{W_NS}}}{tag}"

TEMPLATE = Path("pristine_template.docx")
with zipfile.ZipFile(TEMPLATE, "r") as z:
    file_map = {n: z.read(n) for n in z.namelist()}

tree = ET.fromstring(file_map["word/document.xml"].decode("utf-8"))
body = tree.find(w("body"))

# 1. Modify Page 1
# P0: Title
p0 = body[0]
for t in p0.findall(".//" + w("t")):
    t.text = "FILEVO: POLICY-OPTIMIZED AUTONOMOUS DOCX GENERATION CLI"

# P8: Candidates in red
p8 = body[8]
p8.clear()
p8_pPr = ET.SubElement(p8, w("pPr"))
ET.SubElement(p8_pPr, w("jc"), {w("val"): "center"})
p8_rPr = ET.SubElement(p8_pPr, w("rPr"))
ET.SubElement(p8_rPr, w("rFonts"), {w("ascii"): "Times New Roman", w("hAnsi"): "Times New Roman"})
ET.SubElement(p8_rPr, w("sz"), {w("val"): "24"})

team = [
    ("Harshul Kala",   "1RUA25CSE0188"),
    ("Khushi Krishna", "1RUA25CSE0217"),
    ("Medha Umesh",    "1RUA25CSE0257"),
    ("Meghna Pant",    "1RUA25CSE0259"),
]

for idx, (name, usn) in enumerate(team):
    r = ET.SubElement(p8, w("r"))
    rPr = ET.SubElement(r, w("rPr"))
    ET.SubElement(rPr, w("rFonts"), {w("ascii"): "Times New Roman", w("hAnsi"): "Times New Roman"})
    ET.SubElement(rPr, w("b"))
    ET.SubElement(rPr, w("bCs"))
    ET.SubElement(rPr, w("color"), {w("val"): "ff0000"})
    ET.SubElement(rPr, w("sz"), {w("val"): "24"})
    t = ET.SubElement(r, w("t"), {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    t.text = f"{name} ({usn})"
    if idx < len(team) - 1:
        r_br = ET.SubElement(p8, w("r"))
        ET.SubElement(r_br, w("br"))

# Reduce spacing of empty paragraphs on page 1 so it fits perfectly on 1 page
# Empty paragraphs on page 1: 1, 2, 4, 5, 7, 9, 11, 13, 15, 20, 22, 23, 27
for p_idx in [1, 2, 4, 5, 7, 9, 11, 13, 15, 20, 22, 23, 27]:
    pPr = body[p_idx].find(w("pPr"))
    if pPr is None:
        pPr = ET.SubElement(body[p_idx], w("pPr"))
    sp = pPr.find(w("spacing"))
    if sp is not None:
        pPr.remove(sp)
    ET.SubElement(pPr, w("spacing"), {w("line"): "120", w("lineRule"): "auto", w("after"): "0", w("before"): "0"})

# P28: Month & Year
for t in body[28].findall(".//" + w("t")):
    t.text = "NOVEMBER 2026"

# Insert page break right after P28 so Page 1 terminates exactly after Month & Year
br_p1 = ET.Element(w("p"))
r_br1 = ET.SubElement(br_p1, w("r"))
ET.SubElement(r_br1, w("br"), {w("type"): "page"})
body.insert(29, br_p1)

# Now Page 2 (Declaration)
# P33 is now body[33] (was 32)
p33 = body[33]
runs_p33 = p33.findall(w("r"))
if len(runs_p33) >= 9:
    runs_p33[0].find(w("t")).text = "We, "
    runs_p33[1].find(w("t")).text = "Harshul Kala (1RUA25CSE0188), Khushi Krishna (1RUA25CSE0217), Medha Umesh (1RUA25CSE0257), and Meghna Pant (1RUA25CSE0259), "
    runs_p33[8].find(w("t")).text = "hereby declare that the project work titled “Filevo: Policy-Optimized Autonomous DOCX Generation CLI” has been carried out by us and submitted in partial fulfilment for the award of degree in "

# Write test docx
file_map["word/document.xml"] = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
test_docx = Path("/tmp/test_front.docx")
with zipfile.ZipFile(test_docx, "w", zipfile.ZIP_DEFLATED) as zout:
    for n, d in file_map.items():
        zout.writestr(n, d)

subprocess.run(["soffice", "--headless", "--convert-to", "pdf", str(test_docx), "--outdir", "/tmp/"], check=True)
print("Conversion successful. Check /tmp/test_front.pdf")
