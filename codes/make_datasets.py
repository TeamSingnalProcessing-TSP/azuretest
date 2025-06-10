import os
import csv

def parse_split_series(split_value):
    """
    정수형 SplitSeries 값을 2진수 문자열로 변환한 후,
    5비트씩 나누어 오른쪽부터 읽어 분할 모드(QT, BT_H, BT_V, TT_H, TT_V) 리스트를 반환합니다.
    """
    binary_string = format(split_value, 'b')
    pad_len = ((len(binary_string) + 4) // 5) * 5
    binary_string = binary_string.zfill(pad_len)
    split_groups = [binary_string[i:i+5] for i in range(0, len(binary_string), 5)]
    
    mode_dict = {
        "00001": "QT",     # CU_QUAD_SPLIT
        "00010": "BT_H",   # CU_HORZ_SPLIT
        "00011": "BT_V",   # CU_VERT_SPLIT
        "00100": "TT_H",   # CU_TRIH_SPLIT (수평 TT, 1:2:1 비율)
        "00101": "TT_V"    # CU_TRIV_SPLIT (수직 TT, 1:2:1 비율)
    }
    return [mode_dict.get(bits, "UNKNOWN") for bits in reversed(split_groups)]

def split_cu(prev_x, prev_y, prev_w, prev_h, mode, x, y):
    """
    부모 CU의 좌표와 크기(prev_x, prev_y, prev_w, prev_h) 및 leaf CU의 좌표 (x,y)를 바탕으로,
    지정된 분할 모드(mode)에 따라 하위 CU의 좌표와 크기를 계산하여 반환합니다.
    """
    if mode == "QT":
        new_w = prev_w // 2
        new_h = prev_h // 2
        new_x = prev_x + (new_w if x >= prev_x + new_w else 0)
        new_y = prev_y + (new_h if y >= prev_y + new_h else 0)
        return new_x, new_y, new_w, new_h

    elif mode == "BT_H":
        new_h = prev_h // 2
        new_w = prev_w
        new_x = prev_x
        new_y = prev_y + (new_h if y >= prev_y + new_h else 0)
        return new_x, new_y, new_w, new_h

    elif mode == "BT_V":
        new_w = prev_w // 2
        new_h = prev_h
        new_x = prev_x + (new_w if x >= prev_x + new_w else 0)
        new_y = prev_y
        return new_x, new_y, new_w, new_h

    elif mode == "TT_H":
        # 수평 TT: 부모의 높이를 1:2:1로 분할 (top, middle, bottom)
        h_top = prev_h // 4
        h_mid = prev_h - 2 * h_top
        new_w = prev_w
        new_x = prev_x
        offset_y = y - prev_y
        if offset_y < h_top:
            new_y = prev_y
            new_h = h_top
        elif offset_y < h_top + h_mid:
            new_y = prev_y + h_top
            new_h = h_mid
        else:
            new_y = prev_y + h_top + h_mid
            new_h = prev_h - h_top - h_mid
        return new_x, new_y, new_w, new_h

    elif mode == "TT_V":
        # 수직 TT: 부모의 너비를 1:2:1로 분할 (left, middle, right)
        w_left = prev_w // 4
        w_mid = prev_w - 2 * w_left
        new_h = prev_h
        new_y = prev_y
        offset_x = x - prev_x
        if offset_x < w_left:
            new_x = prev_x
            new_w = w_left
        elif offset_x < w_left + w_mid:
            new_x = prev_x + w_left
            new_w = w_mid
        else:
            new_x = prev_x + w_left + w_mid
            new_w = prev_w - w_left - w_mid
        return new_x, new_y, new_w, new_h

    else:
        return prev_x, prev_y, prev_w, prev_h

def find_parent_cu(poc, pos_str, block_size_str, split_series):
    """
    한 CSV 행(POC, "Pos(x,y)", Block_size(w*h), SplitSeries) 정보를 받아,
    해당 블록이 속한 CTU 내에서 분할 경로(부모 CU 체인)를 계산합니다.
    최종 leaf CU는 "Non_split"으로 표기합니다.
    """
    x, y = map(int, pos_str.strip('"').split(','))
    w, h = map(int, block_size_str.split('*'))
    split_modes = parse_split_series(split_series)
    
    # 블록이 속한 CTU(128×128)의 좌상단 좌표 계산
    ctu_x = (x // 128) * 128
    ctu_y = (y // 128) * 128
    cu_x, cu_y, cu_w, cu_h = ctu_x, ctu_y, 128, 128
    chain = []
    
    # split_series에 기록된 모든 분할 모드를 순차적으로 적용합니다.
    for mode in split_modes:
        chain.append((poc, f"{cu_x},{cu_y}", f"{cu_w}*{cu_h}", mode))
        cu_x, cu_y, cu_w, cu_h = split_cu(cu_x, cu_y, cu_w, cu_h, mode, x, y)
    
    # 최종 leaf CU는 "Non_split"으로 기록합니다.
    tolerance = 1
    if abs(cu_w - w) <= tolerance and abs(cu_h - h) <= tolerance:
        cu_w, cu_h = w, h
    chain.append((poc, f"{cu_x},{cu_y}", f"{cu_w}*{cu_h}", "Non_split"))
    return chain

def process_csv(input_file, output_file):
    """
    input_file을 읽어 각 행마다 분할 경로(부모 CU 체인)를 생성한 후,
    중복되는 (POC, Pos(x,y), Block_size, Split_mode) 항목은 제거하여 output_file에 저장합니다.
    """
    results = []
    with open(input_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            poc = row["POC"]
            pos = row['Pos(x,y)']
            block_size = row["Block_size(w*h)"]
            split_series = int(row["SplitSeries"])
            chain = find_parent_cu(poc, pos, block_size, split_series)
            results.extend(chain)
    
    # 중복 제거
    unique_keys = set()
    unique_results = []
    for entry in results:
        key = tuple(entry)
        if key not in unique_keys:
            unique_results.append(entry)
            unique_keys.add(key)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ["POC", "Pos(x,y)", "Block_size(w*h)", "Split_mode"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for poc, pos, bsize, mode in unique_results:
            writer.writerow({
                "POC": poc,
                "Pos(x,y)": pos,
                "Block_size(w*h)": bsize,
                "Split_mode": mode
            })

def process_all_csv():
    """
    "split_csv" 폴더 내의 모든 CSV 파일을 처리하여,
    결과를 "datasets" 폴더에 [원본 파일 명].csv 형태로 저장합니다.
    """
    input_dir = "split_csv"
    output_dir = "datasets"
    os.makedirs(output_dir, exist_ok=True)
    
    for filename in os.listdir(input_dir):
        if filename.lower().endswith(".csv"):
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            process_csv(input_file, output_file)
            print(f"Processed {input_file} -> {output_file}")

if __name__ == '__main__':
    process_all_csv()
