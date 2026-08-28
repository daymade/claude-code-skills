"""read-docx-review scripts.bridge_lib — 修订感知的 docx 解析层

所有带 tracked changes / comments 的 docx 处理必须走这里，禁止用
python-docx paragraph.text（漏读 <w:ins>）或裸 .//w:t XPath（读到段落级 del）。

机制与三个 csx 的出参规格见本 skill references/csharp-tasks-spec.md。
"""
