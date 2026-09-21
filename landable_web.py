#!/usr/bin/env python3
"""
Landable CUP
A small local web application for maintaining XCSoar landable CUP files.

No external Python packages are required.
"""

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


HOST = "127.0.0.1"
PORT = 8765

CUP_HEADER = "name,code,country,lat,lon,elev,style,rwdir,rwlen,freq,desc"


def decimal_to_lat(value: float) -> str:
    direction = "N" if value >= 0 else "S"
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60
    return f"{degrees:02d}{minutes:06.3f}{direction}"


def decimal_to_lon(value: float) -> str:
    direction = "E" if value >= 0 else "W"
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60
    return f"{degrees:03d}{minutes:06.3f}{direction}"


def cup_to_decimal(value: str) -> float:
    value = value.strip()
    direction = value[-1].upper()
    number = float(value[:-1])
    degrees = int(number // 100)
    minutes = number - degrees * 100
    result = degrees + minutes / 60
    if direction in ("S", "W"):
        result = -result
    return result


def coordinates_to_cup(text: str) -> tuple[str, str]:
    parts = text.replace(",", " ").split()
    if len(parts) != 2:
        raise ValueError("Koordinaatit muodossa latitude,longitude")

    lat = float(parts[0])
    lon = float(parts[1])

    if not -90 <= lat <= 90:
        raise ValueError("Latitude pitää olla välillä -90 ... 90")
    if not -180 <= lon <= 180:
        raise ValueError("Longitude pitää olla välillä -180 ... 180")

    return decimal_to_lat(lat), decimal_to_lon(lon)


def read_cup(path: Path) -> str:
    if not path.exists():
        return f'id="landables"\n{CUP_HEADER}\n'
    return path.read_text(encoding="utf-8")


def split_cup(content: str):
    lines = content.splitlines()

    for index, line in enumerate(lines):
        if line.strip().lower().startswith(
            "name,code,country,lat,lon"
        ):
            return (
                lines[:index],
                lines[index],
                [x for x in lines[index + 1:] if x.strip()],
            )

    return (
        ['id="landables"'],
        CUP_HEADER,
        [x for x in lines if x.strip()],
    )


def write_cup(path: Path, before, header, rows) -> None:
    path.write_text(
        "\n".join(before + [header] + rows) + "\n",
        encoding="utf-8",
    )


def backup(path: Path) -> None:
    if path.exists():
        Path(str(path) + ".bak").write_text(
            path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def make_row(
    name: str,
    code: str,
    coordinates: str,
    elevation: str,
    comment: str,
) -> str:
    lat, lon = coordinates_to_cup(coordinates)

    return ",".join(
        [
            name.strip(),
            code.strip(),
            "FIN",
            lat,
            lon,
            elevation.strip(),
            "3",
            "",
            "",
            "",
            comment.strip(),
        ]
    )


def form_from_row(row: str) -> dict:
    fields = row.split(",", 10)

    if len(fields) != 11:
        return {
            "name": "",
            "code": "",
            "coordinates": "",
            "elevation": "",
            "comment": "",
        }

    try:
        lat = cup_to_decimal(fields[3])
        lon = cup_to_decimal(fields[4])
        coordinates = f"{lat:.14f},{lon:.14f}"
    except Exception:
        coordinates = ""

    return {
        "name": fields[0],
        "code": fields[1],
        "coordinates": coordinates,
        "elevation": fields[5],
        "comment": fields[10],
    }


def append_row(path: Path, row: str) -> None:
    old = read_cup(path)
    before, header, rows = split_cup(old)
    backup(path)
    rows.append(row)
    write_cup(path, before, header, rows)


def update_row(path: Path, index: int, row: str) -> None:
    old = read_cup(path)
    before, header, rows = split_cup(old)

    if not 0 <= index < len(rows):
        raise ValueError("Valittua riviä ei löytynyt")

    backup(path)
    rows[index] = row
    write_cup(path, before, header, rows)


def delete_row(path: Path, index: int) -> None:
    old = read_cup(path)
    before, header, rows = split_cup(old)

    if not 0 <= index < len(rows):
        raise ValueError("Valittua riviä ei löytynyt")

    backup(path)
    del rows[index]
    write_cup(path, before, header, rows)


def send_to_device(source: Path, destination: Path) -> None:
    if not destination:
        raise ValueError("Laitteen CUP-polku ei ole määritetty")

    if not destination.exists():
        raise FileNotFoundError(
            "Laitteen landables.cup ei löydy:\n"
            + str(destination)
        )

    destination.write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


PAGE = """<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landable CUP</title>
<style>
body {
    font-family: system-ui, sans-serif;
    max-width: 1150px;
    margin: 20px auto;
    padding: 0 20px;
    background: #f4f4f4;
    color: #222;
}
h1 { margin-bottom: 4px; }
.info { margin-bottom: 18px; color: #555; }
.layout {
    display: grid;
    grid-template-columns: 1fr 1.5fr;
    gap: 20px;
}
.panel {
    background: white;
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 18px;
}
.mode {
    padding: 9px 10px;
    margin-bottom: 12px;
    background: #eee;
    border-radius: 5px;
}
label {
    display: block;
    font-weight: 600;
    margin-top: 10px;
}
input {
    width: 100%;
    box-sizing: border-box;
    padding: 9px;
    margin-top: 4px;
    font-size: 16px;
}
.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
}
button {
    padding: 10px 16px;
    font-size: 15px;
    cursor: pointer;
}
.update { background: #e8f0ff; }
.new { background: #eeeeee; }
.delete { background: #ffe5e5; }
.device { background: #e5f5e5; }
.device-row { margin-top: 12px; }
select {
    width: 100%;
    height: 430px;
    font-family: monospace;
    font-size: 14px;
}
textarea {
    width: 100%;
    height: 420px;
    box-sizing: border-box;
    font-family: monospace;
    font-size: 14px;
}
.ok {
    padding: 10px;
    margin-bottom: 15px;
    background: #e4f6e4;
    border: 1px solid #9aca9a;
    border-radius: 5px;
}
.error {
    padding: 10px;
    margin-bottom: 15px;
    white-space: pre-wrap;
    background: #ffe5e5;
    border: 1px solid #d99;
    border-radius: 5px;
}
@media (max-width: 800px) {
    .layout { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<h1>Landable CUP</h1>
<div class="info">CUP: <strong>{{FILE}}</strong></div>
{{MESSAGE}}

<div class="layout">

<div class="panel">
<h2>Landable</h2>

<div id="mode" class="mode"><strong>NEW LANDABLE</strong></div>

<form method="post">
<input type="hidden" name="action" id="action" value="add">
<input type="hidden" name="index" id="index" value="-1">

<label>Nimi</label>
<input id="name" name="name" required autocomplete="off">

<label>Koodi</label>
<input id="code" name="code" required autocomplete="off">

<label>Koordinaatit</label>
<input id="coordinates" name="coordinates"
       placeholder="61.56979264141858,22.783633371821683"
       required autocomplete="off">

<label>Korkeus</label>
<input id="elevation" name="elevation"
       placeholder="67m" required autocomplete="off">

<label>Kommentti</label>
<input id="comment" name="comment" autocomplete="off">

<div class="actions">
<button type="submit" onclick="setAction('add')">Add landable</button>
<button type="submit" class="update" onclick="setAction('update')">Update</button>
<button type="button" class="new" onclick="newLandable()">New landable</button>
<button type="submit" class="delete" onclick="return deleteLandable()">Delete</button>
</div>
</form>

<form method="post" class="device-row">
<input type="hidden" name="action" value="device">
<button type="submit" class="device">Vie laitteelle</button>
</form>

<div>{{DEVICE}}</div>
</div>

<div class="panel">
<h2>Landables</h2>

<select id="landables" size="20" onchange="selectRow(this)">
{{OPTIONS}}
</select>

<h2>CUP-tiedosto</h2>
<textarea readonly>{{CONTENT}}</textarea>
</div>

</div>

<script>
const rows = {{ROWS}};

function setAction(action) {
    document.getElementById("action").value = action;
}

function selectRow(select) {
    const index = select.selectedIndex;
    if (index < 0 || !rows[index]) return;

    const r = rows[index];

    document.getElementById("index").value = index;
    document.getElementById("action").value = "update";

    document.getElementById("name").value = r.name;
    document.getElementById("code").value = r.code;
    document.getElementById("coordinates").value = r.coordinates;
    document.getElementById("elevation").value = r.elevation;
    document.getElementById("comment").value = r.comment;

    document.getElementById("mode").innerHTML =
        "<strong>EDITING:</strong> " +
        escapeHtml(r.name) + " [" + escapeHtml(r.code) + "]";
}

function newLandable() {
    document.getElementById("name").value = "";
    document.getElementById("code").value = "";
    document.getElementById("coordinates").value = "";
    document.getElementById("elevation").value = "";
    document.getElementById("comment").value = "";

    document.getElementById("index").value = "-1";
    document.getElementById("action").value = "add";
    document.getElementById("landables").selectedIndex = -1;

    document.getElementById("mode").innerHTML =
        "<strong>NEW LANDABLE</strong>";

    document.getElementById("name").focus();
}

function deleteLandable() {
    const index = document.getElementById("index").value;

    if (index === "-1") {
        alert("Valitse ensin poistettava landable listalta.");
        return false;
    }

    const name = document.getElementById("name").value;

    if (!confirm("Poistetaanko landable '" + name + "'?")) {
        return false;
    }

    document.getElementById("action").value = "delete";
    return true;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
</script>

</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    cup_path: Path
    device_path: Path | None

    def send_page(self, message=""):
        content = read_cup(self.cup_path)
        _, _, rows = split_cup(content)

        options = []
        data = []

        for i, row in enumerate(rows):
            fields = row.split(",", 10)
            label = (
                f"{i}: {fields[0]} [{fields[1]}]"
                if len(fields) == 11
                else f"{i}: {row}"
            )
            options.append(
                "<option>" + html.escape(label) + "</option>"
            )
            data.append(form_from_row(row))

        if self.device_path is None:
            device = (
                '<span style="color:#777">'
                "Laite: ei määritetty"
                "</span>"
            )
        elif self.device_path.exists():
            device = (
                '<span style="color:green">'
                "Laite: landables.cup löytyy"
                "</span>"
            )
        else:
            device = (
                '<span style="color:#a00000">'
                "Laite: landables.cup ei löydy"
                "</span>"
            )

        page = PAGE
        page = page.replace(
            "{{FILE}}", html.escape(str(self.cup_path))
        )
        page = page.replace("{{MESSAGE}}", message)
        page = page.replace("{{OPTIONS}}", "\n".join(options))
        page = page.replace(
            "{{CONTENT}}", html.escape(content)
        )
        page = page.replace(
            "{{ROWS}}",
            json.dumps(data, ensure_ascii=False)
        )
        page = page.replace("{{DEVICE}}", device)

        body = page.encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        self.send_page()

    def do_POST(self):
        if self.path != "/":
            self.send_error(404)
            return

        try:
            length = int(
                self.headers.get("Content-Length", "0")
            )
            raw = self.rfile.read(length)

            form = parse_qs(
                raw.decode("utf-8"),
                keep_blank_values=True
            )

            def get(name):
                return form.get(name, [""])[0].strip()

            action = get("action")

            if action == "device":
                if self.device_path is None:
                    raise ValueError(
                        "Laitteen CUP-polku ei ole määritetty. "
                        "Käynnistä ohjelma --device-path -optiolla."
                    )

                send_to_device(
                    self.cup_path,
                    self.device_path
                )

                self.send_page(
                    '<div class="ok">'
                    "Uusin CUP-tiedosto vietiin laitteelle."
                    "</div>"
                )
                return

            if action == "delete":
                delete_row(
                    self.cup_path,
                    int(get("index"))
                )
                self.send_page(
                    '<div class="ok">'
                    "Landable poistettu."
                    "</div>"
                )
                return

            row = make_row(
                get("name"),
                get("code"),
                get("coordinates"),
                get("elevation"),
                get("comment"),
            )

            if action == "update":
                update_row(
                    self.cup_path,
                    int(get("index")),
                    row,
                )
                message = (
                    '<div class="ok">'
                    "Landable päivitetty."
                    "</div>"
                )
            else:
                append_row(self.cup_path, row)
                message = (
                    '<div class="ok">'
                    "Landable lisätty."
                    "</div>"
                )

            self.send_page(message)

        except Exception as exc:
            self.send_page(
                '<div class="error">'
                + html.escape(str(exc))
                + "</div>"
            )

    def log_message(self, fmt, *args):
        print(
            f"[web] {self.address_string()} - "
            f"{fmt % args}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Local web editor for XCSoar landable CUP files."
    )
    parser.add_argument(
        "cup_file",
        help="CUP file to edit",
    )
    parser.add_argument(
        "--device-path",
        help=(
            "Existing landables.cup on the connected device. "
            "It is replaced by the current CUP when "
            "'Vie laitteelle' is pressed."
        ),
    )
    parser.add_argument(
        "--host",
        default=HOST,
        help=f"Bind address (default: {HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help=f"Port (default: {PORT})",
    )

    args = parser.parse_args()

    Handler.cup_path = (
        Path(args.cup_file).expanduser().resolve()
    )

    Handler.device_path = (
        Path(args.device_path).expanduser()
        if args.device_path
        else None
    )

    print()
    print(f"CUP:    {Handler.cup_path}")
    print(f"Web:    http://{args.host}:{args.port}/")

    if Handler.device_path:
        print(f"Device: {Handler.device_path}")
    else:
        print("Device: not configured")

    print("Ctrl-C lopettaa")
    print()

    server = ThreadingHTTPServer(
        (args.host, args.port),
        Handler,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLopetetaan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
