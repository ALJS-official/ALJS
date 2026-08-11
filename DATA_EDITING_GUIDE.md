# ALJS 赛事数据维护指南

## 1. 页面结构

所有比赛现在共用 `match/index.html`。不要再为 Season 新建 HTML。

- `data/competitions.json`：控制赛事分类、名称、显示顺序和数据文件。
- `data/match/*.json`：每个赛事的具体积分/选手数据。
- URL 示例：`match/?event=s15`。

## 2. 新增一个正赛 Season 16

1. 复制 `data/match/_template.json` 为 `data/match/s16.json`。
2. 填入真实比赛数据。
3. 在 `data/competitions.json` 的 `official.events` 最前面加入：

```json
{
  "id": "s16",
  "name": "ALJS Season 16",
  "shortName": "Season 16",
  "title": "ALJS TOURNAMENT - SEASON 16",
  "dataFile": "data/match/s16.json",
  "date": "2026-00-00",
  "winner": "TEAM",
  "description": "第16届ALJS"
}
```

不需要新增 HTML。

## 3. 新增娱乐赛

娱乐赛名称不受 Season 限制。比如要新增“情侣杯决赛”：

1. 复制 `_template.json` 为 `data/match/couple-cup-final.json`。
2. 在 `competitions.json` 的 `fun.events` 加入：

```json
{
  "id": "couple-cup-final",
  "name": "ALJS 情侣杯决赛",
  "shortName": "情侣杯",
  "title": "ALJS COUPLE CUP - GRAND FINAL",
  "dataFile": "data/match/couple-cup-final.json",
  "date": "2026-00-00",
  "winner": "",
  "description": ""
}
```

页面地址自动成为 `match/?event=couple-cup-final`。

## 4. 暂时没有数据

把赛事的 `dataFile` 设为 `null`：

```json
"dataFile": null
```

页面会只显示 `NO DATA AVAILABLE`，没有提示框。

## 5. 删除赛事

从 `data/competitions.json` 中删除对应赛事对象即可。如果以后也不再使用，可以同时删除对应 `data/match/*.json`。

## 6. 修改赛事名称、日期或冠军

只改 `data/competitions.json` 中对应字段，不用改 HTML。

## 7. 修改比赛积分

在赛事 JSON 中：

- `num_matches`：比赛局数。
- `team_id`：队伍显示名称。
- `total.points`：总分。
- `total.kills`：总击杀。
- `matches.match1.points`：第 1 局得分。
- `matches.match1.placement`：第 1 局排名。
- `matches.match1.kills`：第 1 局击杀。
- `players`：该队选手列表。
- `player_id`：选手名。
- `player.total`：选手全场统计。
- `player.matches.match1`：选手第 1 局统计。

增加一局时，既要把 `num_matches` 加 1，也要在每支队伍的 `matches` 和每个选手的 `matches` 中加入对应 `matchN`。
