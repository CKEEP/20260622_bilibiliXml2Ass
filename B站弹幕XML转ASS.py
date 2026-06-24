# -*- coding: utf-8 -*-
"""
B站弹幕 XML 转 ASS 字幕工具

输入目录路径，自动扫描所有XML文件，转换为ASS字幕文件。
ASS文件放在目录表层，原始XML文件移入 XML_Backup 子目录。

用法: 终端运行 python B站弹幕XML转ASS.py  或双击运行后输入路径
"""

import os
import sys
import shutil
import xml.etree.ElementTree as ET

# === 渲染参数 ===
PLAY_RES_X = 1920
PLAY_RES_Y = 1080
SCROLL_SPEED = 150.0          # 滚动速度(像素/秒), 越小越慢
STATIC_DURATION = 5.0         # 固定弹幕停留秒数
FONT_SIZE = 38                # 默认字号
ROW_HEIGHT = 56               # 滚动弹幕行高(含间距)
TOP_MARGIN = 30
BOTTOM_MARGIN = 80            # 底部留空, 避开播放器进度条
FONT_NAME = "Microsoft YaHei"


def decimal_to_ass_color(dec: int) -> str:
    """B站十进制颜色 -> ASS &HBBGGRR&"""
    r = (dec >> 16) & 0xFF
    g = (dec >> 8) & 0xFF
    b = dec & 0xFF
    return f"&H00{b:02X}{g:02X}{r:02X}"


def format_ass_time(seconds: float) -> str:
    """秒 -> ASS时间 H:MM:SS.cc"""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def escape_ass_text(text: str) -> str:
    """清理弹幕文本并转义 ASS 特殊字符"""
    text = text.replace("\r", "").replace("\n", " ").strip()
    # ASS 中 { } \ 是覆盖标签边界,必须转义,否则会破坏整行渲染
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def assign_row(start_time: float, end_time: float, rows: list[float]) -> int:
    """为滚动弹幕分配行号(避免重叠)"""
    for i, free_at in enumerate(rows):
        if free_at <= start_time:
            rows[i] = end_time
            return i
    earliest = min(range(len(rows)), key=lambda i: rows[i])
    rows[earliest] = max(rows[earliest], start_time) + (end_time - start_time)
    return earliest


def build_ass_lines(danmakus: list) -> list:
    """将弹幕列表转为 ASS Events 行列表"""
    row_count = max(1, (PLAY_RES_Y - TOP_MARGIN - BOTTOM_MARGIN) // ROW_HEIGHT)
    row_free_at = [0.0] * row_count
    lines = []

    for t, mode, fontsize, color_dec, text in sorted(danmakus, key=lambda d: d[0]):
        text = escape_ass_text(text)
        if not text:
            continue

        ass_color = decimal_to_ass_color(color_dec)
        fs = max(18, min(fontsize, 60))
        text_px = len(text) * fs

        if mode == 6:  # 逆向滚动 (从左向右)
            duration = max(4.0, (PLAY_RES_X + text_px) / SCROLL_SPEED)
            end_time = t + duration
            row = assign_row(t, end_time, row_free_at)
            y = TOP_MARGIN + row * ROW_HEIGHT + fs // 2
            x1 = -text_px // 2
            x2 = PLAY_RES_X + text_px // 2
            effect = f"{{\\an2\\move({x1},{y},{x2},{y})\\fs{fs}\\1c{ass_color}}}"
        elif mode in (1, 2, 3):  # 正向滚动 (从右向左)
            duration = max(4.0, (PLAY_RES_X + text_px) / SCROLL_SPEED)
            end_time = t + duration
            row = assign_row(t, end_time, row_free_at)
            y = TOP_MARGIN + row * ROW_HEIGHT + fs // 2
            x1 = PLAY_RES_X + text_px // 2
            x2 = -text_px // 2
            effect = f"{{\\an2\\move({x1},{y},{x2},{y})\\fs{fs}\\1c{ass_color}}}"
        elif mode == 5:  # 顶部固定
            end_time = t + STATIC_DURATION
            y = TOP_MARGIN + fs // 2
            effect = f"{{\\an8\\pos({PLAY_RES_X // 2},{y})\\fs{fs}\\1c{ass_color}}}"
        elif mode == 4:  # 底部固定
            end_time = t + STATIC_DURATION
            y = PLAY_RES_Y - BOTTOM_MARGIN
            effect = f"{{\\an2\\pos({PLAY_RES_X // 2},{y})\\fs{fs}\\1c{ass_color}}}"
        else:  # 其他模式按滚动处理
            duration = max(4.0, (PLAY_RES_X + text_px) / SCROLL_SPEED)
            end_time = t + duration
            row = assign_row(t, end_time, row_free_at)
            y = TOP_MARGIN + row * ROW_HEIGHT + fs // 2
            x1 = PLAY_RES_X + text_px // 2
            x2 = -text_px // 2
            effect = f"{{\\an2\\move({x1},{y},{x2},{y})\\fs{fs}\\1c{ass_color}}}"

        lines.append(
            f"Dialogue: 0,{format_ass_time(t)},{format_ass_time(end_time)},"
            f"Default,,0,0,0,,{effect}{text}"
        )

    return lines


def convert_xml_to_ass(xml_path: str, ass_path: str) -> int:
    """单个XML转ASS, 返回弹幕条数"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    danmakus = []
    for d in root.iter("d"):
        p_attr = d.get("p") or ""
        parts = p_attr.split(",")
        if len(parts) < 8:
            continue
        try:
            t = float(parts[0])
            mode = int(parts[1])
            fontsize = int(parts[2])
            color = int(parts[3])
        except ValueError:
            continue
        text = (d.text or "").strip()
        if text:
            danmakus.append((t, mode, fontsize, color, text))

    if not danmakus:
        return 0

    lines = [
        "[Script Info]",
        "; B站弹幕 XML 转 ASS 工具",
        "Title: Bilibili Danmaku",
        "ScriptType: v4.00+",
        "Collisions: Normal",
        f"PlayResX: {PLAY_RES_X}",
        f"PlayResY: {PLAY_RES_Y}",
        "Timer: 100.0000",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
         "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
         "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
         "Alignment, MarginL, MarginR, MarginV, Encoding"),
        (f"Style: Default,{FONT_NAME},{FONT_SIZE},&H00FFFFFF,&H000000FF,"
         f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1.5,0,2,0,0,0,134"),
        "",
        "[Events]",
        ("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
         "Effect, Text"),
    ]

    lines.extend(build_ass_lines(danmakus))

    with open(ass_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    return len(danmakus)


def main():
    print("=" * 50)
    print("  B站弹幕 XML -> ASS 字幕转换器")
    print("=" * 50)
    print()

    # 支持命令行参数
    if len(sys.argv) > 1:
        work_dir = sys.argv[1].strip().strip('"').strip("'")
    else:
        work_dir = input("请输入包含XML文件的目录路径: ").strip().strip('"').strip("'")

    if not work_dir:
        print("未输入路径，已退出。")
        return
    if not os.path.isdir(work_dir):
        print(f"错误: 目录 '{work_dir}' 不存在。")
        input("\n按回车键退出...")
        return

    xml_files = sorted(
        f for f in os.listdir(work_dir)
        if f.lower().endswith(".xml") and os.path.isfile(os.path.join(work_dir, f))
    )
    if not xml_files:
        print(f"在 '{work_dir}' 中未找到 XML 弹幕文件。")
        input("\n按回车键退出...")
        return

    print(f"找到 {len(xml_files)} 个 XML 文件，开始转换...\n")

    backup_dir = os.path.join(work_dir, "XML_Backup")
    os.makedirs(backup_dir, exist_ok=True)

    success = 0
    for xml_name in xml_files:
        xml_path = os.path.join(work_dir, xml_name)
        ass_name = os.path.splitext(xml_name)[0] + ".ass"
        ass_path = os.path.join(work_dir, ass_name)

        try:
            count = convert_xml_to_ass(xml_path, ass_path)
            if count == 0:
                print(f"  [跳过] {xml_name} (无弹幕数据,XML 保留在原位置)")
                continue
            backup_path = os.path.join(backup_dir, xml_name)
            if os.path.exists(backup_path):
                base, ext = os.path.splitext(xml_name)
                i = 1
                while os.path.exists(os.path.join(backup_dir, f"{base}_{i}{ext}")):
                    i += 1
                backup_path = os.path.join(backup_dir, f"{base}_{i}{ext}")
            shutil.move(xml_path, backup_path)
            print(f"  [OK] {xml_name}  ({count} 条弹幕)")
            success += 1
        except ET.ParseError as e:
            print(f"  [XML解析失败] {xml_name}: {e}")
        except Exception as e:
            print(f"  [失败] {xml_name}: {e}")

    print("\n" + "-" * 50)
    print(f"完成: 成功 {success} / 总数 {len(xml_files)}")
    print(f"ASS 字幕: {work_dir}")
    print(f"XML 备份: {backup_dir}")
    print("-" * 50)
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
