#!/opt/homebrew/opt/python@3.9/bin/python3.9
# -*- coding: utf-8 -*-
"""
从 ecdict.csv 制作英汉词典 MDX 文件。

用法:
    ./make_mdx.py                              # 全量词典
    ./make_mdx.py --single-only                # 仅保留单个单词
    ./make_mdx.py --max-frq 5000               # 仅保留 FRQ 前 5000 热门词
    ./make_mdx.py --single-only --max-frq 5000 # 组合过滤

输出:
    - ECDICT 英汉词典.txt   (MDX 源文本，可手动检查)
    - ECDICT 英汉词典.mdx   (MDX 词典文件，可直接在 MDict 中使用)
"""

import argparse
import csv
import os
import sys

from mdict_utils.writer import pack_mdx_txt, pack

CSV_FILE = os.path.join(os.path.dirname(__file__), "ecdict.csv")
BASE_NAME = "ECDICT 英汉词典"

# CSV 列索引
COL_WORD = 0
COL_PHONETIC = 1
COL_DEFINITION = 2
COL_TRANSLATION = 3
COL_POS = 4
COL_COLLINS = 5
COL_OXFORD = 6
COL_TAG = 7
COL_BNC = 8
COL_FRQ = 9


def build_definition(phonetic, translation, pos):
    """构建极简 HTML 格式的释义（减小 MDX 体积）"""
    parts = []

    if phonetic:
        parts.append(f"<i>/{phonetic}/</i>")

    if pos:
        if translation:
            parts.append(f"<b>{pos}</b>")
        else:
            parts.append(f"{pos}")

    if translation:
        trans = translation.replace("\\n", "<br>").replace("\n", "<br>")
        if parts:
            parts.append(f"<br>{trans}")
        else:
            parts.append(trans)

    return "".join(parts)


def parse_args():
    parser = argparse.ArgumentParser(
        description="从 ecdict.csv 制作英汉词典 MDX 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                           # 全量词典 (768K 词条, ~17MB)
  %(prog)s -s                        # 仅保留单词语 (403K 词条)
  %(prog)s -f 5000                   # FRQ 前 5000 热门词
  %(prog)s -c 3                      # 柯林斯 3 星及以上
  %(prog)s -s -f 10000               # 单词语 + FRQ 前 10000
  %(prog)s -s -c 1 -f 20000          # 单词语 + 有评级 + FRQ 前 20000
        """,
    )
    parser.add_argument(
        "-s", "--single-only",
        action="store_true",
        help="仅保留单个单词（排除短语、带撇号/连字符开头的词）",
    )
    parser.add_argument(
        "-f", "--max-frq", "--top-frq",
        type=int,
        default=0,
        metavar="N",
        help="仅保留 FRQ 词频排名前 N 的词（如 5000 表示前 5000 热门词）",
    )
    parser.add_argument(
        "-c", "--min-collins",
        type=int,
        default=0,
        metavar="N",
        help="最低柯林斯星级 (1-5，如 3 表示 3 星及以上)",
    )
    parser.add_argument(
        "-o", "--min-oxford",
        type=int,
        default=0,
        metavar="N",
        help="最低牛津星级 (1-5)",
    )
    return parser.parse_args()


def is_single_word(word):
    """判断是否为单个单词（排除短语及特殊前缀词）"""
    return " " not in word and not word.startswith("'") and not word.startswith("-")


def should_include(args, word, row):
    """根据过滤参数判断是否保留该词条"""
    # 单词语过滤
    if args.single_only and not is_single_word(word):
        return False

    # 柯林斯星级
    if args.min_collins > 0:
        try:
            collins = int(row[COL_COLLINS]) if row[COL_COLLINS] else 0
        except (ValueError, IndexError):
            collins = 0
        if collins < args.min_collins:
            return False

    # 牛津星级
    if args.min_oxford > 0:
        try:
            oxford = int(row[COL_OXFORD]) if row[COL_OXFORD] else 0
        except (ValueError, IndexError):
            oxford = 0
        if oxford < args.min_oxford:
            return False

    # FRQ 词频排名（越小越热门）
    if args.max_frq > 0:
        try:
            frq = int(row[COL_FRQ]) if row[COL_FRQ] else 0
        except (ValueError, IndexError):
            frq = 0
        # frq=0 表示无排名数据，不纳入热门过滤
        if frq == 0 or frq > args.max_frq:
            return False

    return True


def main():
    args = parse_args()

    if not os.path.exists(CSV_FILE):
        print(f"错误: 找不到 {CSV_FILE}")
        sys.exit(1)

    # 构建输出文件名（反映过滤条件）
    suffix_parts = []
    if args.single_only:
        suffix_parts.append("单词语")
    if args.max_frq > 0:
        suffix_parts.append(f"热门前{args.max_frq}")
    if args.min_collins > 0:
        suffix_parts.append(f"柯林斯{args.min_collins}星")
    if args.min_oxford > 0:
        suffix_parts.append(f"牛津{args.min_oxford}星")

    suffix = "_" + "-".join(suffix_parts) if suffix_parts else ""
    output_txt = os.path.join(os.path.dirname(__file__), f"{BASE_NAME}{suffix}.txt")
    output_mdx = os.path.join(os.path.dirname(__file__), f"{BASE_NAME}{suffix}.mdx")

    # 第一步：读取 CSV，收集并过滤词条
    print(f"正在读取 {CSV_FILE} ...")
    if args.single_only:
        print("  过滤: 仅保留单个单词")
    if args.max_frq > 0:
        print(f"  过滤: FRQ 词频排名前 {args.max_frq}")
    if args.min_collins > 0:
        print(f"  过滤: 柯林斯 {args.min_collins} 星及以上")
    if args.min_oxford > 0:
        print(f"  过滤: 牛津 {args.min_oxford} 星及以上")

    total = 0
    skipped_total = 0
    entries = []

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # 跳过表头

        for row in reader:
            total += 1
            if total % 50000 == 0:
                print(f"  已处理 {total} 条 ...")

            if len(row) < 5:
                skipped_total += 1
                continue

            word = row[COL_WORD].strip()
            if not word:
                skipped_total += 1
                continue

            # 过滤条件
            if not should_include(args, word, row):
                skipped_total += 1
                continue

            phonetic = row[COL_PHONETIC].strip() if len(row) > COL_PHONETIC else ""
            translation = row[COL_TRANSLATION].strip() if len(row) > COL_TRANSLATION else ""
            pos = row[COL_POS].strip() if len(row) > COL_POS else ""

            if not phonetic and not translation and not pos:
                skipped_total += 1
                continue

            definition = build_definition(phonetic, translation, pos)
            entries.append((word, definition))

    print(f"共 {total} 条，跳过 {skipped_total} 条，有效词条 {len(entries)} 条")

    # 第二步：全局排序
    print("正在排序 ...")
    entries.sort(key=lambda x: x[0].lower())

    # 第三步：写入 MDX 源文本
    print(f"正在写入 MDX 源文本: {output_txt} ...")
    with open(output_txt, "w", encoding="utf-8") as f:
        for word, definition in entries:
            f.write(f"{word}\n{definition}\n</>\n")
    print(f"  -> {output_txt}")

    # 第四步：将 TXT 打包为 MDX
    txt_size = os.path.getsize(output_txt)
    print(f"\n正在打包 MDX（源文本 {txt_size / 1024 / 1024:.0f} MB）...")
    print("  使用 Compact HTML 模式压缩 ...")

    dictionary = pack_mdx_txt(output_txt, encoding="UTF-8")
    pack(output_mdx, dictionary,
         title="ECDICT 英汉词典",
         description="ECDICT 英汉词典，包含音标、词性和中文释义",
         encoding="UTF-8")

    mdx_size = os.path.getsize(output_mdx)
    ratio = (1 - mdx_size / txt_size) * 100
    print(f"  -> {output_mdx}")
    print(f"\n结果对比:")
    print(f"  源文本: {txt_size / 1024 / 1024:.0f} MB")
    print(f"  MDX 词典: {mdx_size / 1024 / 1024:.1f} MB (压缩 {ratio:.0f}%)")
    print("完成！")


if __name__ == "__main__":
    main()
