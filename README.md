# generate_dot_map.py

輪郭で描かれた地図のSVGを、等間隔に並べた単色の円（ドット）でできたドット絵風のSVGに変換するツールです。

指定した範囲（例：日本）だけ、ドットの色・大きさ・間隔を変えて強調することもできます。

## 動作環境

- Python 3（標準ライブラリのみで動作。追加のパッケージは不要）

## 使い方

```sh
python3 generate_dot_map.py -i <入力SVG> -s <ドット間隔> [-o <出力SVG>]
```

入力の地図は `maps/` に、出力は `output/` に置きます。`-o` を省略すると、`output/<入力ファイル名>-dot.svg` に出力します（例：`maps/world.svg` なら `output/world-dot.svg`）。出力先のフォルダがなければ自動で作ります。

コマンドはプロジェクトのフォルダ（`generate_dot_map.py` がある場所）で実行してください。既定の入力・出力のパスは、実行した場所からの相対パスです。

### 例：日本地図（都道府県）

```sh
python3 generate_dot_map.py -i maps/japan-map-full.svg -s 10 -c "#888888" -r 0.42
```

### 例：世界地図

```sh
python3 generate_dot_map.py -i maps/world.svg -s 10 -c "#888888" -r 0.42
```

### 例：太平洋中心の世界地図で、日本だけ赤く細かいドットにする

```sh
python3 generate_dot_map.py \
    -i "maps/World_map_(Mercator_projection)_Pacific-centric.svg" \
    -s 4 -c "#888888" -r 0.42 \
    --highlight-polygon "333,226.5 349,226.5 350,242 342,256 322,268 312,284 302,284 306,268 312,258 316,250 322,245 330,238" \
    --highlight-color "#e60012" --highlight-step 2 --highlight-radius-ratio 0.45 \
    -o output/world-pacific-dot.svg
```

実行すると、ドットの数などが表示されます。

```
dots=5632 highlighted=47 cols=182 rows=94 step=4.0 -> output/world-pacific-dot.svg
```

## オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `-i`, `--input` | `maps/japan-map-full.svg` | 入力SVGファイル |
| `-o`, `--output` | `output/<入力ファイル名>-dot.svg` | 出力SVGファイル。フォルダがなければ作る |
| `-s`, `--step` | `10` | ドットの間隔（入力SVGの座標単位） |
| `-c`, `--color` | `#888888` | ドットの色 |
| `-r`, `--radius-ratio` | `0.42` | ドットの半径（間隔に対する比率）。0.5で隣のドットと接する |
| `--highlight-polygon` | なし | 強調する範囲の多角形。`"x,y x,y ..."` の形で、入力SVGの座標で指定する |
| `--highlight-color` | `#e60012` | 強調範囲のドットの色 |
| `--highlight-step` | `--step` と同じ | 強調範囲のドットの間隔 |
| `--highlight-radius-ratio` | `0.6` | 強調範囲のドットの半径（`--highlight-step` に対する比率） |

### ドットの間隔の目安

`--step` は入力SVGの座標単位で指定します。そのため、同じ値でも地図の大きさによってドットの細かさが変わります。地図の幅をドットの横の数で割った値を目安にしてください。

| 入力SVG | 幅 | 例 |
|---|---|---|
| `maps/japan-map-full.svg` | 約1000 | `-s 10` で横約100個 |
| `maps/world.svg` | 2000 | `-s 10` で横約200個 |
| `maps/World_map_(Mercator_projection)_Pacific-centric.svg` | 約720 | `-s 4` で横約180個 |

## 仕組み

1. 入力SVGから `<path>` と `<polygon>` を読み込み、多角形の集まりに変換します。`<g>` の `transform`（`matrix` / `translate` / `scale`）も反映します。
2. 地図全体を囲む範囲に、`--step` の間隔で格子状に点を並べます。
3. 各点がいずれかの多角形の内側にあれば「陸地」とみなし、そこに円を置きます。
4. 出力SVGの表示範囲（`viewBox`）は、陸地の範囲に1間隔分の余白を足した大きさになります。

### 強調範囲の扱い

`--highlight-polygon` を指定すると、次のように処理します。

- 強調範囲の中には、通常のドットを置きません。
- 強調範囲の中の陸地には、`--highlight-step` の間隔で別にドットを置きます。この格子は通常の格子と同じ原点から数えるので、`--step` が `--highlight-step` の整数倍なら、ドットの並びがずれません。
- 強調ドットは通常のドットより後に書き出すため、重なった場合は上に表示されます。

入力SVGに国や地域の区切りがない場合（例：`maps/World_map_(Mercator_projection)_Pacific-centric.svg` は陸地全体が1つの `<path>`）は、強調したい地域のまわりを多角形で手動で囲みます。隣の地域（日本なら朝鮮半島・サハリン・千島列島・台湾）が入らないように、出力を見ながら座標を調整してください。

## 制限事項

- 陸地の判定には `<path>` と `<polygon>` だけを使います。`<rect>`、`<circle>`、`<ellipse>`、`<use>` などは無視します。
- `transform` は `matrix`、`translate`、`scale` に対応しています。`rotate` と `skew` は無視します。
- 曲線（`C` / `S` / `Q` / `T` / `A`）は、終点どうしを直線でつないだ形として扱います。細かい曲線が多い地図では、輪郭が少し変わることがあります。
- パスの中にある穴（内側の輪郭）も陸地として扱います。湖などが穴として描かれている地図では、湖の部分にもドットが置かれます。
- 要素の `fill`、`display`、CSSなどは見ません。非表示の要素や枠線用の要素も、閉じた形であれば陸地として扱います。
- 出力SVGの `<title>` は常に `Dot art map` になります。

## ファイル構成

```
.
├── README.md
├── generate_dot_map.py          変換ツール本体
├── maps/                        入力の地図
│   ├── japan-map-full.svg       日本の都道府県地図（Geolonia）
│   ├── world.svg                世界地図（Simplemaps）
│   └── World_map_(Mercator_projection)_Pacific-centric.svg
│                                太平洋中心のメルカトル図法の世界地図
└── output/                      出力のドット絵SVG
```

## 入力データの出典とライセンス

入力SVGは外部で作成された地図データです。変換後のドット絵を配布・公開する場合は、元データのライセンスに従って出典を表示してください。

- `maps/japan-map-full.svg`：Geolonia（https://geolonia.com/）作成。
- `maps/world.svg`：Simplemaps（http://simplemaps.com）作成。MIT License。ファイル内の表記は「Copyright (c) 2020 Pareto Softare, LLC DBA Simplemaps.com」（綴りは原文のまま）。
- `maps/World_map_(Mercator_projection)_Pacific-centric.svg`：ファイル内に出典・ライセンスの記載がないため、入手元で確認してください。
