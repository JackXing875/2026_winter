import pandas as pd
import time
import random
import json
import os
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
CSV_FILE = '/home/schrieffer/2026_winter/data/questions.csv'
OUTPUT_FILE = 'doubao_answers.json'
DOUBAO_URL = 'https://www.doubao.com/chat/'
# ----------------

def check_captcha_pause(page, is_first_question=False):
    """
    遇到验证码暂停，等待用户手动解决。
    """
    has_captcha = False
    try:
        # 检测常见的验证码关键词
        if page.get_by_text("安全验证").is_visible() or \
           page.get_by_text("拖动滑块").is_visible() or \
           page.locator('.captcha-verify-container').count() > 0:
            has_captcha = True
    except: pass

    if is_first_question or has_captcha:
        print("\n" + "!"*50)
        print("【等待人工介入】")
        print("1. 请查看浏览器，是否有验证码？")
        print("2. 如果有，请手动完成拖拽。")
        print("3. 等待【答案开始生成】（看到字在动了）。")
        print("!"*50)
        input(">>> 确认已过验证且答案正在生成？按 [Enter] 继续抓取...")
        print(">>> 恢复运行...")

def get_active_answer_text(page):
    """
    【最长文本优先策略】
    扫描页面所有可能的文本块，返回字数最多的那一段。
    这样可以完美避开底部的“复制”、“重新生成”等短文本干扰。
    """
    # 增加更多可能的选择器，确保不漏
    selectors = [
        'div[data-testid="message-card-content"]',
        '.markdown-body',         # 豆包正文最常用的类
        '.msg-content',
        '.message-content',
        'div[class*="text-message"]',
        'div[class*="content"]'   # 兜底
    ]
    
    # 黑名单（绝对不要的）
    ignore_texts = ["文件数量", "上传文档", "重新生成", "搜索", "加载失败"]
    
    max_len = 0
    best_text = ""
    
    # 收集所有候选文本
    for sel in selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                text = el.inner_text().strip()
                
                # 过滤垃圾
                if not text: continue
                if any(x in text for x in ignore_texts): continue
                
                # 【核心逻辑】：谁长选谁
                # 只有当新找到的文本比当前记录的更长时，才替换
                if len(text) > max_len:
                    max_len = len(text)
                    best_text = text
        except:
            continue

    return best_text

def run_automation():
    # 读取 CSV (简略版)
    try:
        df = pd.read_csv(CSV_FILE)
        # 寻找问题列
        target_col = next((c for c in df.columns if 'question' in c.lower() or '问题' in c), df.columns[0])
        questions = df[target_col].tolist()
        print(f"成功加载 {len(questions)} 个问题。")
    except Exception as e:
        print(f"读取 CSV 失败: {e}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=['--start-maximized'])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        page.goto(DOUBAO_URL)
        print("\n=== 请登录 ===")
        input(">>> 登录成功并进入聊天界面后，按 [Enter] 开始脚本...")

        # 定位输入框
        input_selector = 'div[contenteditable="true"]'
        
        # 循环提问
        for index, q in enumerate(questions):
            q = str(q).strip()
            if not q: continue
            
            print(f"\n[{index+1}/{len(questions)}] 提问: {q[:10]}...")

            try:
                # 1. 寻找并聚焦输入框
                try:
                    page.wait_for_selector(input_selector, timeout=5000)
                    page.click(input_selector)
                except:
                    # 备选方案：尝试找 textarea
                    page.click('textarea')
                
                # 2. 输入并发送
                page.keyboard.press('Control+A')
                page.keyboard.press('Backspace')
                time.sleep(0.5)
                page.keyboard.type(q, delay=30)
                time.sleep(0.5)
                page.keyboard.press('Enter')
                
                # 3. 暂停检测验证码
                time.sleep(2)
                check_captcha_pause(page, is_first_question=(index == 0))

                # 4. 监听答案生成 (Debug 模式)
                print(">>> 开始监听答案...")
                last_text = ""
                stable_start_time = time.time()
                wait_timeout = time.time()
                
                debug_counter = 0

                while True:
                    # 尝试获取当前文本
                    current_text = get_active_answer_text(page)
                    
                    # --- DEBUG 输出 (每10次循环输出一次，避免刷屏) ---
                    if debug_counter % 5 == 0:
                        preview = current_text[:20].replace('\n', ' ') if current_text else "未找到文本"
                        print(f"\r[监控中] 当前抓取长度: {len(current_text)} | 内容预览: {preview}...", end="")
                    debug_counter += 1
                    # -----------------------------------------------

                    # 逻辑 A: 字数在增加 -> 正在生成
                    if len(current_text) > len(last_text):
                        last_text = current_text
                        stable_start_time = time.time() # 重置稳定计时器
                        wait_timeout = time.time()      # 重置超时计时器
                    
                    # 逻辑 B: 字数不变 -> 可能完成，也可能卡住
                    else:
                        # 如果有内容，且超过 4 秒没变 -> 认为完成
                        if len(current_text) > 5 and (time.time() - stable_start_time > 4):
                            print(f"\n>>> 判定回答完成！(长度: {len(current_text)})")
                            break
                        
                        # 如果内容一直是空的，或者一直是用户的问题(长度短)，等待
                        pass

                    # 逻辑 C: 超时保护 (比如 30秒 长度都没变过，或者一直抓不到)
                    if time.time() - wait_timeout > 60:
                        print("\n>>> [超时] 长时间未检测到有效生成。")
                        # 可能是脚本抓错元素了，或者验证码卡住了
                        check_captcha_pause(page)
                        wait_timeout = time.time() # 再给一次机会
                        # 如果确认没问题，就跳过
                        if input(">>> 跳过此题吗？(y/n): ").lower() == 'y':
                            break
                    
                    time.sleep(0.8)

                # 5. 存盘
                entry = {"id": index+1, "question": q, "answer": last_text}
                
                existing_data = []
                if os.path.exists(OUTPUT_FILE):
                    try:
                        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                    except: pass
                
                existing_data.append(entry)
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)

                # 休息
                print(f">>> 成功保存。休息中...")
                time.sleep(random.randint(5, 10))

            except Exception as e:
                print(f"!!! 异常: {e}")
                input(">>> 按回车重试...")

        print("全部完成")
        browser.close()

if __name__ == "__main__":
    run_automation()