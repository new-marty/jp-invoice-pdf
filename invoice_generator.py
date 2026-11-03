#!/usr/bin/env python3
"""
請求書 (Invoice) PDF Generator
===============================
時給ベースのシンプルな請求書 (内税・インボイス登録番号欄つき) を生成するPythonスクリプト。
発行者・請求先・時給などは JSON 設定ファイルに書く (invoice.example.json を参照)。

使い方:
    python invoice_generator.py --hours 40                       # ./invoice.json を読んで生成
    python invoice_generator.py --config my.json --hours 40      # 設定ファイルを指定
    python invoice_generator.py --hours 40 --rate 6000 -o out.pdf
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ============================================================
# Configuration
# ============================================================

DEFAULT_CONFIG = "invoice.json"
DEFAULT_HOURS = 0            # 稼働時間
DEFAULT_TAX_RATE = Decimal("0.10")  # 消費税率 10%

# --- テーマカラー ---
THEME_COLOR = colors.HexColor("#1a1a1a")      # Black
THEME_COLOR_LIGHT = colors.HexColor("#f5f5f5") # Light gray for alternating rows
TEXT_COLOR = colors.HexColor("#1a1a1a")
GRAY_COLOR = colors.HexColor("#666666")
LINE_COLOR = colors.HexColor("#cccccc")

# ============================================================
# Font Setup
# ============================================================

def setup_fonts(font_path=None):
    """日本語フォントの登録 (font_path 指定 > fonts/ の Noto > OS のフォント)"""
    # Noto Serif JP (明朝系) — formal, professional look for invoices
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if not font_path:
        font_path = os.path.join(script_dir, "fonts", "NotoSerifJP.ttf")

    if not os.path.exists(font_path):
        # Fallback to Sans
        font_path = os.path.join(script_dir, "fonts", "NotoSansJP.ttf")

    if not os.path.exists(font_path):
        for path in [
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        ]:
            if os.path.exists(path):
                font_path = path
                break

    if not font_path or not os.path.exists(font_path):
        print("Error: No Japanese TTF font found.")
        sys.exit(1)

    pdfmetrics.registerFont(TTFont("NotoSansJP", font_path))
    pdfmetrics.registerFont(TTFont("NotoSansJP-Bold", font_path))
    pdfmetrics.registerFont(TTFont("NotoSansJP-Medium", font_path))
    pdfmetrics.registerFont(TTFont("NotoSansJP-Light", font_path))

    return {"NotoSansJP": True, "NotoSansJP-Bold": True}


# ============================================================
# Invoice Data
# ============================================================

class InvoiceData:
    """請求書データを格納するクラス"""

    def __init__(self, **kwargs):
        now = datetime.now()
        next_month_end = (now.replace(day=1) + timedelta(days=62)).replace(day=1) - timedelta(days=1)

        self.invoice_number = kwargs.get("invoice_number",
            f"INV-{now.strftime('%Y%m%d')}-1")
        self.issue_date = kwargs.get("issue_date",
            f"{now.year}年{now.month}月{now.day}日")
        self.due_date = kwargs.get("due_date",
            f"{next_month_end.year}年{next_month_end.month}月{next_month_end.day}日")

        self.client_name = kwargs["client_name"]
        self.client_address = kwargs.get("client_address", "")

        self.issuer = kwargs["issuer"]

        self.hours = Decimal(str(kwargs.get("hours", DEFAULT_HOURS)))
        self.hourly_rate = Decimal(str(kwargs["hourly_rate"]))
        self.description = kwargs.get("description", "")
        self.tax_rate = Decimal(str(kwargs.get("tax_rate", DEFAULT_TAX_RATE)))

        self.notes = kwargs.get("notes", "お振込手数料は貴社でご負担をお願いいたします。")

        # 追加明細行 (オプション)
        # [{"description": "交通費", "quantity": 1, "unit": "式", "unit_price": 700}, ...]
        self.extra_items = kwargs.get("extra_items", [])

    @property
    def subtotal(self) -> Decimal:
        """税込金額の小計"""
        total = self.hours * self.hourly_rate
        for item in self.extra_items:
            total += Decimal(str(item.get("quantity", 1))) * Decimal(str(item["unit_price"]))
        return total

    @property
    def tax_included_amount(self) -> Decimal:
        """税込合計 = 小計 (すでに税込)"""
        return self.subtotal

    @property
    def tax_amount(self) -> Decimal:
        """内税方式の消費税額"""
        return (self.subtotal * self.tax_rate / (1 + self.tax_rate)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP)

    @property
    def pre_tax_amount(self) -> Decimal:
        """税抜金額"""
        return self.subtotal - self.tax_amount


# ============================================================
# PDF Generator
# ============================================================

class InvoicePDFGenerator:
    """請求書PDFを生成するクラス"""

    def __init__(self, data: InvoiceData):
        self.data = data
        self.width, self.height = A4  # 210mm x 297mm
        self.margin_left = 20 * mm
        self.margin_right = 20 * mm
        self.margin_top = 20 * mm
        self.content_width = self.width - self.margin_left - self.margin_right

    def generate(self, output_path: str):
        """PDFファイルを生成"""
        c = canvas.Canvas(output_path, pagesize=A4)
        c.setTitle("請求書")

        y = self.height - self.margin_top
        y = self._draw_header(c, y)
        y = self._draw_parties(c, y)
        y = self._draw_amount_box(c, y)
        y = self._draw_items_table(c, y)
        y = self._draw_totals(c, y)
        y = self._draw_tax_breakdown(c, y)
        y = self._draw_bank_info(c, y)

        c.save()
        print(f"✅ 請求書を生成しました: {output_path}")

    def _fmt_currency(self, amount) -> str:
        """金額フォーマット"""
        return f"¥{int(amount):,}"

    def _draw_header(self, c, y) -> float:
        """ヘッダー: タイトル + 発行日 + 請求書番号"""
        # 上部のアクセントライン
        c.setStrokeColor(THEME_COLOR)
        c.setLineWidth(3)
        c.line(self.margin_left, y, self.width - self.margin_right, y)

        y -= 15 * mm

        # タイトル
        c.setFont("NotoSansJP-Bold", 22)
        c.setFillColor(TEXT_COLOR)
        title = "請 求 書"
        title_width = c.stringWidth(title, "NotoSansJP-Bold", 22)
        c.drawString((self.width - title_width) / 2, y, title)

        y -= 10 * mm

        # 発行日・請求書番号 (右寄せ)
        right_x = self.width - self.margin_right
        c.setFont("NotoSansJP", 9)
        c.setFillColor(GRAY_COLOR)
        c.drawRightString(right_x, y, f"発行日: {self.data.issue_date}")
        y -= 4.5 * mm
        c.drawRightString(right_x, y, f"請求書番号: {self.data.invoice_number}")

        y -= 10 * mm
        return y

    def _draw_parties(self, c, y) -> float:
        """請求先と発行者情報"""
        left_x = self.margin_left
        right_x = self.width / 2 + 10 * mm

        # --- 請求先 (左側) ---
        c.setFont("NotoSansJP-Bold", 13)
        c.setFillColor(TEXT_COLOR)
        c.drawString(left_x, y, f"{self.data.client_name}  御中")

        # 下線
        y -= 2 * mm
        c.setStrokeColor(TEXT_COLOR)
        c.setLineWidth(0.5)
        name_width = c.stringWidth(f"{self.data.client_name}  御中", "NotoSansJP-Bold", 13)
        c.line(left_x, y, left_x + name_width + 5 * mm, y)

        y -= 6 * mm

        # 件名 (クライアント住所があれば表示)
        if self.data.client_address:
            c.setFont("NotoSansJP", 8)
            c.setFillColor(GRAY_COLOR)
            for line in self.data.client_address.split("\n"):
                c.drawString(left_x, y, line)
                y -= 4 * mm

        # --- 発行者情報 (右側) ---
        info = self.data.issuer
        ry = y + 12 * mm  # 右側は少し上から始める

        c.setFont("NotoSansJP-Bold", 11)
        c.setFillColor(TEXT_COLOR)
        c.drawString(right_x, ry, info["name"])
        ry -= 5 * mm

        c.setFont("NotoSansJP", 8)
        c.setFillColor(GRAY_COLOR)

        if info.get("registration_number"):
            c.drawString(right_x, ry, f"登録番号: {info['registration_number']}")
            ry -= 4 * mm

        if info.get("postal_code"):
            c.drawString(right_x, ry, info["postal_code"])
            ry -= 4 * mm

        if info.get("address"):
            for line in info["address"].split("\n"):
                c.drawString(right_x, ry, line)
                ry -= 4 * mm

        y = min(y, ry) - 5 * mm
        return y

    def _draw_amount_box(self, c, y) -> float:
        """ご請求金額ボックス"""
        box_x = self.margin_left
        box_width = 80 * mm
        box_height = 12 * mm

        # ラベル
        c.setFont("NotoSansJP", 9)
        c.setFillColor(GRAY_COLOR)
        c.drawString(box_x, y, "下記のとおりご請求申し上げます。")
        y -= 8 * mm

        # ボックス
        c.setStrokeColor(THEME_COLOR)
        c.setLineWidth(1.5)
        c.roundRect(box_x, y - box_height + 3 * mm, box_width, box_height,
                    2 * mm, fill=0, stroke=1)

        c.setFillColor(TEXT_COLOR)
        c.setFont("NotoSansJP-Bold", 10)
        c.drawString(box_x + 4 * mm, y - box_height + 7 * mm, "ご請求金額")

        c.setFont("NotoSansJP-Bold", 14)
        amount_str = self._fmt_currency(self.data.tax_included_amount)
        c.drawRightString(box_x + box_width - 4 * mm, y - box_height + 6.5 * mm, amount_str)

        y -= box_height + 5 * mm
        return y

    def _draw_payment_deadline(self, c, y) -> float:
        """お支払期限"""
        c.setFont("NotoSansJP", 9)
        c.setFillColor(TEXT_COLOR)
        c.drawString(self.margin_left, y, f"お支払期限: {self.data.due_date}")
        y -= 10 * mm
        return y

    def _draw_items_table(self, c, y) -> float:
        """明細テーブル"""
        left_x = self.margin_left
        table_width = self.content_width
        row_height = 10 * mm
        header_height = 9 * mm

        # カラム定義: (ラベル, x_start_ratio, width_ratio, alignment)
        cols = [
            ("品目",   0.00, 0.60, "left"),
            ("数量",   0.60, 0.20, "right"),
            ("金額",   0.80, 0.20, "right"),
        ]

        # --- ヘッダー ---
        c.setFillColor(THEME_COLOR)
        c.rect(left_x, y - header_height, table_width, header_height, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont("NotoSansJP-Bold", 9)
        for label, x_ratio, w_ratio, align in cols:
            col_x = left_x + table_width * x_ratio
            col_w = table_width * w_ratio
            if align == "right":
                c.drawRightString(col_x + col_w - 4 * mm, y - header_height + 3 * mm, label)
            else:
                c.drawString(col_x + 4 * mm, y - header_height + 3 * mm, label)

        y -= header_height

        # --- 明細行 ---
        items = []

        # メイン: 稼働時間
        if self.data.hours > 0:
            hours_display = f"{self.data.hours:g}"
            rate_display = self._fmt_currency(self.data.hourly_rate)
            items.append({
                "description": f"{self.data.description}（税込{rate_display}/h）",
                "quantity": f"{hours_display}h",
                "amount": self._fmt_currency(self.data.hours * self.data.hourly_rate),
            })

        # 追加明細
        for item in self.data.extra_items:
            qty = item.get("quantity", 1)
            price = item["unit_price"]
            unit = item.get("unit", "式")
            items.append({
                "description": item["description"],
                "quantity": f"{qty}{unit}",
                "amount": self._fmt_currency(Decimal(str(qty)) * Decimal(str(price))),
            })

        # 空行を追加して最低4行にする
        while len(items) < 4:
            items.append({"description": "", "quantity": "", "amount": ""})

        c.setFont("NotoSansJP", 9)
        for i, item in enumerate(items):
            row_y = y - row_height

            # 交互の背景色
            if i % 2 == 0:
                c.setFillColor(THEME_COLOR_LIGHT)
                c.rect(left_x, row_y, table_width, row_height, fill=1, stroke=0)

            # 下線
            c.setStrokeColor(LINE_COLOR)
            c.setLineWidth(0.3)
            c.line(left_x, row_y, left_x + table_width, row_y)

            c.setFillColor(TEXT_COLOR)
            values = [item["description"], item["quantity"], item["amount"]]
            for j, (label, x_ratio, w_ratio, align) in enumerate(cols):
                col_x = left_x + table_width * x_ratio
                col_w = table_width * w_ratio
                if align == "right":
                    c.drawRightString(col_x + col_w - 4 * mm, row_y + 3.5 * mm, values[j])
                else:
                    c.drawString(col_x + 4 * mm, row_y + 3.5 * mm, values[j])

            y = row_y

        # テーブル下線
        c.setStrokeColor(THEME_COLOR)
        c.setLineWidth(1.5)
        c.line(left_x, y, left_x + table_width, y)

        y -= 8 * mm
        return y

    def _draw_totals(self, c, y) -> float:
        """合計欄"""
        right_x = self.width - self.margin_right
        label_x = right_x - 70 * mm
        value_x = right_x - 4 * mm
        row_h = 7 * mm

        rows = [
            ("小計", self._fmt_currency(self.data.subtotal), "NotoSansJP", 9),
            (f"消費税 ({int(self.data.tax_rate * 100)}% 内税)", self._fmt_currency(self.data.tax_amount), "NotoSansJP", 9),
        ]

        for label, value, font, size in rows:
            c.setFont(font, size)
            c.setFillColor(GRAY_COLOR)
            c.drawString(label_x, y, label)
            c.setFillColor(TEXT_COLOR)
            c.drawRightString(value_x, y, value)

            # 下線
            y -= 2 * mm
            c.setStrokeColor(LINE_COLOR)
            c.setLineWidth(0.3)
            c.line(label_x, y, right_x, y)
            y -= row_h

        # 合計 (強調)
        y -= 1 * mm
        c.setFont("NotoSansJP-Bold", 12)
        c.setFillColor(TEXT_COLOR)
        c.drawString(label_x, y, "合計")
        c.drawRightString(value_x, y, self._fmt_currency(self.data.tax_included_amount))

        y -= 3 * mm
        c.setStrokeColor(TEXT_COLOR)
        c.setLineWidth(1.5)
        c.line(label_x, y, right_x, y)

        y -= 12 * mm
        return y

    def _draw_tax_breakdown(self, c, y) -> float:
        """税率区分"""
        right_x = self.width - self.margin_right
        box_width = 75 * mm
        box_x = right_x - box_width
        row_h = 7 * mm

        # ヘッダー
        c.setFillColor(THEME_COLOR)
        c.rect(box_x, y - row_h, box_width, row_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("NotoSansJP-Bold", 8)

        col_w = box_width / 3
        c.drawCentredString(box_x + col_w * 0.5, y - row_h + 2 * mm, "税率区分")
        c.drawCentredString(box_x + col_w * 1.5, y - row_h + 2 * mm, "対象額")
        c.drawCentredString(box_x + col_w * 2.5, y - row_h + 2 * mm, "消費税")
        y -= row_h

        # 10%行
        c.setStrokeColor(LINE_COLOR)
        c.setLineWidth(0.3)
        c.rect(box_x, y - row_h, box_width, row_h, fill=0, stroke=1)
        c.setFillColor(TEXT_COLOR)
        c.setFont("NotoSansJP", 8)
        c.drawCentredString(box_x + col_w * 0.5, y - row_h + 2 * mm, "10%対象")
        c.drawCentredString(box_x + col_w * 1.5, y - row_h + 2 * mm,
                           self._fmt_currency(self.data.pre_tax_amount))
        c.drawCentredString(box_x + col_w * 2.5, y - row_h + 2 * mm,
                           self._fmt_currency(self.data.tax_amount))

        # 縦線
        for i in range(1, 3):
            lx = box_x + col_w * i
            c.line(lx, y, lx, y - row_h)

        y -= row_h + 8 * mm
        return y

    def _draw_bank_info(self, c, y) -> float:
        """振込先"""
        left_x = self.margin_left
        info = self.data.issuer

        c.setFont("NotoSansJP-Bold", 10)
        c.setFillColor(THEME_COLOR)
        c.drawString(left_x, y, "振込先")
        y -= 3 * mm

        c.setStrokeColor(THEME_COLOR)
        c.setLineWidth(0.8)
        c.line(left_x, y, left_x + 60 * mm, y)
        y -= 6 * mm

        # ボックス
        box_height = 18 * mm
        c.setStrokeColor(LINE_COLOR)
        c.setLineWidth(0.5)
        c.roundRect(left_x, y - box_height, self.content_width, box_height,
                    2 * mm, fill=0, stroke=1)

        c.setFont("NotoSansJP", 9)
        c.setFillColor(TEXT_COLOR)
        iy = y - 5 * mm
        bank_line = f"{info.get('bank_name', '')}  {info.get('branch_name', '')}  {info.get('account_type', '')}  {info.get('account_number', '')}"
        c.drawString(left_x + 4 * mm, iy, bank_line)
        iy -= 5 * mm
        c.drawString(left_x + 4 * mm, iy, f"口座名義: {info.get('account_holder', '')}")

        y -= box_height + 8 * mm
        return y

    def _draw_notes(self, c, y) -> float:
        """備考"""
        left_x = self.margin_left

        c.setFont("NotoSansJP-Bold", 10)
        c.setFillColor(THEME_COLOR)
        c.drawString(left_x, y, "備考")
        y -= 3 * mm

        c.setStrokeColor(THEME_COLOR)
        c.setLineWidth(0.8)
        c.line(left_x, y, left_x + 60 * mm, y)
        y -= 6 * mm

        if self.data.notes:
            box_height = 15 * mm
            c.setStrokeColor(LINE_COLOR)
            c.setLineWidth(0.5)
            c.roundRect(left_x, y - box_height, self.content_width, box_height,
                        2 * mm, fill=0, stroke=1)

            c.setFont("NotoSansJP", 9)
            c.setFillColor(TEXT_COLOR)
            for i, line in enumerate(self.data.notes.split("\n")):
                c.drawString(left_x + 4 * mm, y - 5 * mm - (i * 4.5 * mm), line)

            y -= box_height + 5 * mm

        return y


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="請求書PDF生成ツール")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG,
                        help=f"JSON設定ファイルパス (デフォルト: {DEFAULT_CONFIG})")
    parser.add_argument("--hours", type=float, default=None,
                        help="稼働時間")
    parser.add_argument("--rate", type=int, default=None,
                        help="税込時給 (円)。設定ファイルの hourly_rate を上書き")
    parser.add_argument("--description", type=str, default=None,
                        help="作業内容の説明")
    parser.add_argument("--client", type=str, default=None,
                        help="請求先名")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="出力ファイルパス")
    parser.add_argument("--invoice-number", type=str, default=None,
                        help="請求書番号")
    parser.add_argument("--due-date", type=str, default=None,
                        help="支払期限 (例: 2025年3月31日)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: 設定ファイル {args.config} がありません。"
              "invoice.example.json をコピーして書き換えてください。")
        sys.exit(1)
    with open(args.config, "r", encoding="utf-8") as f:
        kwargs = json.load(f)

    # コマンドライン引数で上書き
    overrides = {
        "hours": args.hours,
        "hourly_rate": args.rate,
        "description": args.description,
        "client_name": args.client,
        "invoice_number": args.invoice_number,
        "due_date": args.due_date,
    }
    kwargs.update({k: v for k, v in overrides.items() if v is not None})

    missing = [k for k in ("issuer", "client_name", "hourly_rate") if k not in kwargs]
    if missing:
        print(f"Error: 設定ファイルに {', '.join(missing)} がありません。")
        sys.exit(1)

    font_path = kwargs.pop("font_path", None)
    if font_path:
        # 相対パスは設定ファイルの場所から解決する
        font_path = os.path.join(os.path.dirname(os.path.abspath(args.config)),
                                 os.path.expanduser(font_path))
    setup_fonts(font_path)

    data = InvoiceData(**kwargs)

    # 出力パス
    output = args.output or f"invoice_{datetime.now().strftime('%Y%m%d')}.pdf"

    generator = InvoicePDFGenerator(data)
    generator.generate(output)


if __name__ == "__main__":
    main()
