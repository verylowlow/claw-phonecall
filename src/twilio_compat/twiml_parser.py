import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_twiml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    stream_url = None
    parameters: dict[str, str] = {}

    for el in root.iter():
        if _local_name(el.tag) != "Stream":
            continue
        stream_url = el.get("url")
        for child in el:
            if _local_name(child.tag) != "Parameter":
                continue
            name = child.get("name")
            if name is not None:
                parameters[name] = child.get("value") or ""
        break

    return {"stream_url": stream_url, "parameters": parameters}
