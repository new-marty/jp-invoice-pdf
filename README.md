# jp-invoice-pdf

時給で働いた分の請求書を、日本の書式の PDF にする Python スクリプトです。
金額は内税(税込時給)で計算し、税率区分の表とインボイスの登録番号欄、振込先を載せます。

## 使い方

```sh
pip install -r requirements.txt
cp invoice.example.json invoice.json   # 発行者・請求先・時給・口座を書き換える
python invoice_generator.py --hours 40 -o invoice_2026-10.pdf
```

`invoice.json` には住所や口座番号が入るので、`.gitignore` で除外しています。
別の場所に置くときは `--config path/to/invoice.json` で指定します。

| オプション | 意味 |
|---|---|
| `--hours` | 稼働時間 |
| `--rate` | 税込時給(設定ファイルの `hourly_rate` を上書き) |
| `--description` | 明細の品目 |
| `--client` | 請求先名 |
| `--invoice-number` | 請求書番号(省略時は `INV-YYYYMMDD-1`) |
| `--due-date` | 支払期限 |
| `-o`, `--output` | 出力先(省略時は `invoice_YYYYMMDD.pdf`) |

## 設定ファイル

`invoice.example.json` が雛形です。必須は `issuer`(発行者と振込先)、`client_name`、`hourly_rate` の 3 つです。
交通費などを足すときは `extra_items` に `{"description": "交通費", "quantity": 1, "unit": "式", "unit_price": 700}` の形で並べます。

## フォント

`font_path` に日本語の TTF を指定するか、`fonts/NotoSerifJP.ttf`(なければ `fonts/NotoSansJP.ttf`)を置きます。
Noto Serif JP は [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Serif+JP) から入手できます。
どれもなければ OS のフォント(macOS の AppleGothic など)を使います。

## License

MIT
