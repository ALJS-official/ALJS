#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
normalize_aljs_xlsx.py

读取当前目录中的：
    1.xlsx
    2.xlsx
    3.xlsx
    4.xlsx
    ...

并合并成 ALJS 网站 match 页面可直接读取的 JSON。

不依赖 pandas / openpyxl。
使用 Python 标准库直接读取 .xlsx 内部 XML。

已知 Excel 前 15 列：
A  #          -> 忽略
B  player     -> player_id
C  team       -> team_id
D  score      -> 本局队伍 points
E  kills      -> 个人 kills
F  legend     -> 忽略
G  damage     -> 个人 damage
H  downs      -> knockdowns
I  assists    -> assists
J  time       -> avg_survival / 用于恢复本局 placement
K  headshots  -> 忽略
L  hits       -> 忽略
M  shots      -> 忽略
N  respawns   -> respawns
O  revives    -> revives

输出：
    match.json

用法：
    python normalize_aljs_xlsx.py

指定输出名：
    python normalize_aljs_xlsx.py -o couple-cup-final.json

指定输入文件夹：
    python normalize_aljs_xlsx.py -i G:\\a\\ALJS-neo\\norm -o match.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from posixpath import normpath, join as posix_join


# ============================================================
# 可选配置
# ============================================================

# 如果需要统一队名，在这里写：
# TEAM_RENAMES = {
#     "SK": "SKD",
#     "WB": "JH",
# }
TEAM_RENAMES: dict[str, str] = {}

# 如果某些队伍是测试队、不想写进 JSON：
# EXCLUDE_TEAMS = {"TEST"}
EXCLUDE_TEAMS: set[str] = set()


# ============================================================
# Excel 列号（0-based）
# ============================================================

COL_NUMBER = 0       # A #
COL_PLAYER = 1       # B player
COL_TEAM = 2         # C team
COL_SCORE = 3        # D score
COL_KILLS = 4        # E kills
COL_LEGEND = 5       # F legend
COL_DAMAGE = 6       # G damage
COL_DOWNS = 7        # H downs
COL_ASSISTS = 8      # I assists
COL_TIME = 9         # J time
COL_HEADSHOTS = 10   # K headshots
COL_HITS = 11        # L hits
COL_SHOTS = 12       # M shots
COL_RESPAWNS = 13    # N respawns
COL_REVIVES = 14     # O revives

REQUIRED_COLUMNS = 15


# ============================================================
# XLSX 读取器（纯标准库）
# ============================================================

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {
    "m": NS_MAIN,
    "r": NS_REL_DOC,
    "pr": NS_REL_PKG,
}


def column_letters_to_index(cell_ref: str) -> int:
    """A -> 0, B -> 1, AA -> 26"""
    m = re.match(r"^([A-Z]+)", cell_ref.upper())
    if not m:
        return 0

    result = 0
    for ch in m.group(1):
        result = result * 26 + (ord(ch) - ord("A") + 1)

    return result - 1


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"

    if path not in zf.namelist():
        return []

    root = ET.fromstring(zf.read(path))
    strings = []

    for si in root.findall(f"{{{NS_MAIN}}}si"):
        # 支持普通字符串和 rich text
        texts = []
        for t in si.iter(f"{{{NS_MAIN}}}t"):
            texts.append(t.text or "")
        strings.append("".join(texts))

    return strings


def get_first_sheet_path(zf: zipfile.ZipFile) -> str:
    """
    找 workbook 中的第一个 worksheet，不假设一定叫 sheet1.xml。
    """
    workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))

    sheets = workbook_root.find(f"{{{NS_MAIN}}}sheets")
    if sheets is None or len(sheets) == 0:
        raise ValueError("Excel 中没有 worksheet。")

    first_sheet = list(sheets)[0]
    rel_id = first_sheet.attrib.get(f"{{{NS_REL_DOC}}}id")

    if not rel_id:
        raise ValueError("无法取得第一个 worksheet 的 relationship id。")

    rels_root = ET.fromstring(
        zf.read("xl/_rels/workbook.xml.rels")
    )

    target = None

    for rel in rels_root:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target")
            break

    if not target:
        raise ValueError("无法定位第一个 worksheet 文件。")

    # relationship target 通常是 worksheets/sheet1.xml
    if target.startswith("/"):
        path = target.lstrip("/")
    else:
        path = normpath(posix_join("xl", target))

    if path not in zf.namelist():
        raise ValueError(f"Worksheet 文件不存在：{path}")

    return path


def read_xlsx_rows(path: Path) -> list[list[object]]:
    """
    返回第一张 worksheet 的所有行。
    保留空单元格的位置。
    """
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings = load_shared_strings(zf)
        sheet_path = get_first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))

        sheet_data = root.find(f"{{{NS_MAIN}}}sheetData")
        if sheet_data is None:
            return []

        rows_out = []

        for row_node in sheet_data.findall(f"{{{NS_MAIN}}}row"):
            values_by_col: dict[int, object] = {}
            max_col = -1

            for cell in row_node.findall(f"{{{NS_MAIN}}}c"):
                ref = cell.attrib.get("r", "")
                col_idx = column_letters_to_index(ref)
                max_col = max(max_col, col_idx)

                cell_type = cell.attrib.get("t")
                value: object = ""

                if cell_type == "inlineStr":
                    is_node = cell.find(f"{{{NS_MAIN}}}is")
                    if is_node is not None:
                        texts = [
                            t.text or ""
                            for t in is_node.iter(f"{{{NS_MAIN}}}t")
                        ]
                        value = "".join(texts)

                else:
                    v = cell.find(f"{{{NS_MAIN}}}v")

                    if v is not None and v.text is not None:
                        raw = v.text

                        if cell_type == "s":
                            try:
                                value = shared_strings[int(raw)]
                            except (ValueError, IndexError):
                                value = raw

                        elif cell_type in ("str", "e"):
                            value = raw

                        elif cell_type == "b":
                            value = raw == "1"

                        else:
                            # 数字
                            try:
                                num = float(raw)
                                if num.is_integer():
                                    value = int(num)
                                else:
                                    value = num
                            except ValueError:
                                value = raw

                values_by_col[col_idx] = value

            if max_col < 0:
                continue

            row = [""] * (max_col + 1)

            for col_idx, value in values_by_col.items():
                row[col_idx] = value

            rows_out.append(row)

        return rows_out


# ============================================================
# 数据转换
# ============================================================

def cell(row: list[object], index: int) -> object:
    if index >= len(row):
        return ""
    return row[index]


def to_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_int(value: object, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if math.isnan(value):
            return default
        return int(round(value))

    text = str(value).strip()
    if not text:
        return default

    # 兼容 "18.0"
    try:
        return int(float(text))
    except ValueError:
        return default


def normalize_team_id(raw: object) -> str:
    """
    例如：
        10_WTD   -> WTD
        12_CHA   -> CHA
        2_NONAME -> NONAME
    """
    text = to_text(raw)

    m = re.match(r"^\s*\d+_(.+?)\s*$", text)
    team_id = m.group(1).strip() if m else text

    return TEAM_RENAMES.get(team_id, team_id)


def parse_time_seconds(value: object) -> int | None:
    """
    支持：
      17m 02s
      17m02s
      17:02
      00:17:02
      Excel 原生时间小数（一天的 fraction）
    """
    if value is None or value == "":
        return None

    # Excel 原生 time 值，比如 0.0118 天
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        num = float(value)

        if 0 <= num < 1:
            return int(round(num * 24 * 60 * 60))

        # 如果就是秒数，也容忍
        if 1 <= num <= 24 * 60 * 60:
            return int(round(num))

    text = str(value).strip()
    if not text:
        return None

    # 17m 02s
    m = re.match(
        r"^\s*(\d+)\s*m(?:in)?\s*(\d+)\s*s(?:ec)?s?\s*$",
        text,
        re.I,
    )
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    # 17:02
    m = re.match(r"^\s*(\d+):(\d{1,2})\s*$", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))

    # 00:17:02
    m = re.match(r"^\s*(\d+):(\d{1,2}):(\d{1,2})\s*$", text)
    if m:
        return (
            int(m.group(1)) * 3600
            + int(m.group(2)) * 60
            + int(m.group(3))
        )

    return None


def format_time(seconds: int | float | None) -> str:
    if seconds is None:
        return "/"

    total = int(round(seconds))
    minutes, secs = divmod(total, 60)

    return f"{minutes}m {secs:02d}s"


def parse_game_file(path: Path, game_no: int) -> list[dict]:
    rows = read_xlsx_rows(path)
    parsed = []

    for excel_row_no, row in enumerate(rows, start=1):
        # 至少要求 A:O 的信息存在；缺尾部空列也没关系，cell() 会返回 ""
        player = to_text(cell(row, COL_PLAYER))
        team_id = normalize_team_id(cell(row, COL_TEAM))

        score = to_int(cell(row, COL_SCORE))
        kills = to_int(cell(row, COL_KILLS))
        damage = to_int(cell(row, COL_DAMAGE))
        downs = to_int(cell(row, COL_DOWNS))
        assists = to_int(cell(row, COL_ASSISTS))
        respawns = to_int(cell(row, COL_RESPAWNS))
        revives = to_int(cell(row, COL_REVIVES))
        survival_seconds = parse_time_seconds(cell(row, COL_TIME))

        # 自动跳过表头、空行、说明行
        if not player or not team_id:
            continue

        if score is None or kills is None:
            continue

        if team_id.lower() in {"team", "team name"}:
            continue

        if player.lower() in {"player", "player name"}:
            continue

        if team_id in EXCLUDE_TEAMS:
            continue

        if survival_seconds is None:
            raise ValueError(
                f"{path.name} 第 {excel_row_no} 行："
                f"无法解析 time={cell(row, COL_TIME)!r} "
                f"(player={player}, team={team_id})"
            )

        parsed.append(
            {
                "game_no": game_no,
                "player": player,
                "team_id": team_id,
                "team_points": score,
                "kills": kills,
                "damage": damage or 0,
                "knockdowns": downs or 0,
                "assists": assists or 0,
                "respawns": respawns or 0,
                "revives": revives or 0,
                "survival_seconds": survival_seconds,
            }
        )

    if not parsed:
        raise ValueError(
            f"{path.name} 没有解析到有效数据。"
            f"请确认数据位于第一张 worksheet，且 B:O 列格式与约定一致。"
        )

    return parsed


def discover_game_files(input_dir: Path) -> list[tuple[int, Path]]:
    found = []

    for path in input_dir.iterdir():
        if not path.is_file():
            continue

        m = re.fullmatch(r"(\d+)\.xlsx", path.name, re.I)
        if not m:
            continue

        found.append((int(m.group(1)), path))

    found.sort(key=lambda x: x[0])

    if not found:
        raise FileNotFoundError(
            f"{input_dir.resolve()} 中没有找到 1.xlsx、2.xlsx ... "
        )

    nums = [n for n, _ in found]
    expected = list(range(1, max(nums) + 1))

    if nums != expected:
        missing = sorted(set(expected) - set(nums))
        raise ValueError(
            f"比赛文件编号不连续：{nums}；缺少：{missing}"
        )

    return found


# ============================================================
# Placement
# ============================================================

def infer_game_placements(rows: list[dict], game_no: int) -> dict[str, int]:
    """
    Excel 前 15 列没有 placement，因此用队伍最后存活时间恢复。

    每支队取该局所有选手的最大 time；
    max time 越长，placement 越高。

    若两个队 max time 精确相同：
      1. 本局 score 高者优先
      2. 本局 kills 高者优先
      3. team_id 作为稳定排序

    同时打印 WARNING，方便人工检查极少数同秒情况。
    """
    grouped = defaultdict(list)

    for row in rows:
        grouped[row["team_id"]].append(row)

    summaries = []

    for team_id, members in grouped.items():
        scores = {m["team_points"] for m in members}

        if len(scores) != 1:
            raise ValueError(
                f"Game {game_no} / {team_id}："
                f"同队选手的 score 不一致：{sorted(scores)}"
            )

        score = members[0]["team_points"]
        kills = sum(m["kills"] for m in members)
        max_time = max(m["survival_seconds"] for m in members)

        summaries.append(
            {
                "team_id": team_id,
                "max_time": max_time,
                "score": score,
                "kills": kills,
            }
        )

    # 检查同秒
    time_groups = defaultdict(list)
    for x in summaries:
        time_groups[x["max_time"]].append(x["team_id"])

    for sec, teams in sorted(time_groups.items(), reverse=True):
        if len(teams) > 1:
            print(
                f"WARNING: Game {game_no} 有队伍最后存活时间相同 "
                f"({format_time(sec)}): {', '.join(sorted(teams))}；"
                f"将使用 score/kills 作次级排序。"
            )

    summaries.sort(
        key=lambda x: (
            -x["max_time"],
            -x["score"],
            -x["kills"],
            x["team_id"].casefold(),
        )
    )

    return {
        x["team_id"]: rank
        for rank, x in enumerate(summaries, start=1)
    }


# ============================================================
# JSON 构造
# ============================================================

def blank_player_match() -> dict:
    return {
        "kills": "/",
        "damage": "/",
        "assists": "/",
        "knockdowns": "/",
        "revives": "/",
        "respawns": "/",
        "avg_survival": "/",
    }


def build_json(all_games: dict[int, list[dict]]) -> dict:
    num_matches = max(all_games)

    game_placements = {}
    team_game_rows = defaultdict(lambda: defaultdict(list))
    player_game_rows = defaultdict(dict)

    # 收集
    for game_no, rows in all_games.items():
        placements = infer_game_placements(rows, game_no)
        game_placements[game_no] = placements

        for row in rows:
            team_id = row["team_id"]
            player = row["player"]

            team_game_rows[team_id][game_no].append(row)
            player_game_rows[(team_id, player)][game_no] = row

    teams_out = []

    for team_id, games in team_game_rows.items():
        matches = {}
        total_points = 0
        total_kills = 0
        game_score_vector = []

        for game_no in range(1, num_matches + 1):
            members = games.get(game_no, [])

            if not members:
                matches[f"match{game_no}"] = {
                    "points": 0,
                    "placement": "/",
                    "kills": 0,
                }
                game_score_vector.append(0)
                continue

            scores = {m["team_points"] for m in members}
            if len(scores) != 1:
                raise ValueError(
                    f"Game {game_no} / {team_id}: "
                    f"同队 score 不一致：{sorted(scores)}"
                )

            points = members[0]["team_points"]
            kills = sum(m["kills"] for m in members)
            placement = game_placements[game_no][team_id]

            matches[f"match{game_no}"] = {
                "points": points,
                "placement": placement,
                "kills": kills,
            }

            total_points += points
            total_kills += kills
            game_score_vector.append(points)

        # 玩家
        player_names = sorted(
            player
            for (tid, player) in player_game_rows.keys()
            if tid == team_id
        )

        players_out = []

        for player in player_names:
            pgames = player_game_rows[(team_id, player)]

            pmatches = {}
            total = {
                "kills": 0,
                "damage": 0,
                "assists": 0,
                "knockdowns": 0,
                "revives": 0,
                "respawns": 0,
            }
            survival_values = []

            for game_no in range(1, num_matches + 1):
                row = pgames.get(game_no)

                if row is None:
                    pmatches[f"match{game_no}"] = blank_player_match()
                    continue

                pmatches[f"match{game_no}"] = {
                    "kills": row["kills"],
                    "damage": row["damage"],
                    "assists": row["assists"],
                    "knockdowns": row["knockdowns"],
                    "revives": row["revives"],
                    "respawns": row["respawns"],
                    "avg_survival": format_time(row["survival_seconds"]),
                }

                total["kills"] += row["kills"]
                total["damage"] += row["damage"]
                total["assists"] += row["assists"]
                total["knockdowns"] += row["knockdowns"]
                total["revives"] += row["revives"]
                total["respawns"] += row["respawns"]
                survival_values.append(row["survival_seconds"])

            avg_survival = (
                format_time(sum(survival_values) / len(survival_values))
                if survival_values
                else "/"
            )

            players_out.append(
                {
                    "player_id": player,
                    "total": {
                        **total,
                        "avg_survival": avg_survival,
                    },
                    "matches": pmatches,
                }
            )

        teams_out.append(
            {
                "team_id": team_id,
                "total": {
                    "points": total_points,
                    "placement": 0,
                    "kills": total_kills,
                },
                "matches": matches,
                "players": players_out,

                # 临时 tie-break 字段
                "_game_score_vector": sorted(
                    game_score_vector,
                    reverse=True
                ),
            }
        )

    # ========================================================
    # 最终总榜排名
    #
    # 1) 总 points
    # 2) 最佳单局 score
    # 3) 次佳单局 score ...
    # 4) 总 kills
    # ========================================================
    teams_out.sort(
        key=lambda t: (
            -t["total"]["points"],
            tuple(-x for x in t["_game_score_vector"]),
            -t["total"]["kills"],
            t["team_id"].casefold(),
        )
    )

    for rank, team in enumerate(teams_out, start=1):
        team["total"]["placement"] = rank
        del team["_game_score_vector"]

    return {
        "num_matches": num_matches,
        "teams": teams_out,
    }


# ============================================================
# 主程序
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize ALJS 1.xlsx, 2.xlsx ... "
            "into website match JSON."
        )
    )

    parser.add_argument(
        "-i",
        "--input-dir",
        default=".",
        help="1.xlsx, 2.xlsx ... 所在文件夹；默认当前目录。",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="match.json",
        help="输出 JSON 文件；默认 match.json。",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    try:
        game_files = discover_game_files(input_dir)
        all_games = {}

        print("找到比赛文件：")

        for game_no, path in game_files:
            rows = parse_game_file(path, game_no)
            all_games[game_no] = rows

            team_count = len({r["team_id"] for r in rows})

            print(
                f"  Game {game_no}: {path.name} "
                f"-> {len(rows)} players / {team_count} teams"
            )

        result = build_json(all_games)

        output_path.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print("完成。")
        print(f"比赛局数：{result['num_matches']}")
        print(f"队伍数量：{len(result['teams'])}")
        print(
            "选手数量："
            f"{sum(len(t['players']) for t in result['teams'])}"
        )
        print(f"输出文件：{output_path.resolve()}")

        print()
        print("总榜：")

        for team in result["teams"]:
            t = team["total"]

            print(
                f"  {t['placement']:>2}. "
                f"{team['team_id']:<16} "
                f"{t['points']:>3} pts / "
                f"{t['kills']:>3} kills"
            )

        return 0

    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
