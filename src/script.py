import pandas as pd
import time
import random
import json
import os
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
CSV_FILE = '/home/schrieffer/2026_winter/data/questions.csv'  # 确保文件名和下载的一致
OUTPUT_FILE = 'doubao_answers.json'
DOUBAO_URL = 'https://www.doubao.com/chat/'
# ----------------

def run_automation():
    # 1. 读取 CSV
    try:
        df = pd.read_csv(CSV_FILE)
        # 自动识别那一列是问题
        target_col = None
        for col in df.columns:
            if 'question' in col.lower() or '问题' in col:
                target_col = col
                break
        if not target_col: target_col = df.columns[0] # 没找到就用第一列
        questions = df[target_col].tolist()
        print(f"成功加载 {len(questions)} 个问题。")
    except Exception as e:
        print(f"读取 CSV 失败: {e}")
        return

    with sync_playwright() as p:
        # 启动浏览器
        print(">>> 正在启动浏览器...")
        browser = p.chromium.launch(headless=False, args=['--start-maximized']) # 有头模式
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        # 打开页面
        page.goto(DOUBAO_URL)
        
        print("\n" + "="*60)
        print("【重要提示】")
        print("1. 请现在手动在浏览器中扫码或登录。")
        print("2. 登录成功，看到对话界面后，请不要操作，也不要关闭浏览器！")
        print("3. 回到这里，按 'Enter' (回车键) 开始脚本。")
        print("="*60 + "\n")
        input(">>> 登录完成后，请按回车键继续...")

        # 2. 智能定位输入框 (核心修改)
        # 豆包的输入框通常是一个富文本框 div
        print(">>> 正在寻找输入框...")
        
        input_selector = 'div[contenteditable="true"]' # 方案A: 富文本框
        textarea_selector = 'textarea'                 # 方案B: 纯文本框
        
        try:
            # 等待输入框出现，最多等 30秒
            # 优先找 contenteditable，如果找不到找 textarea
            page.wait_for_selector(f'{input_selector}, {textarea_selector}', timeout=30000)
            
            # 判断到底存在的是哪一个
            if page.is_visible(input_selector):
                final_selector = input_selector
            else:
                final_selector = textarea_selector
                
            print(f">>> 找到输入框，使用选择器: {final_selector}")
            
            # 点击一下聚焦，确保页面是活的
            page.click(final_selector)
            
        except Exception as e:
            print(f"!!! 致命错误: 找不到输入框。请确认您已登录并进入了聊天界面。")
            print(f"错误信息: {e}")
            return

        # 3. 开始循环提问
        for index, q in enumerate(questions):
            if not str(q).strip(): continue # 跳过空行
            
            print(f"\n[{index+1}/{len(questions)}] 正在提问: {q[:10]}...")
            
            try:
                # A. 清空并输入问题
                page.click(final_selector)
                # 全选删除旧内容（防止上次没发出去）
                page.keyboard.press('Control+A') 
                page.keyboard.press('Backspace')
                
                # 模拟打字
                page.keyboard.type(str(q), delay=50) 
                time.sleep(0.5)
                
                # B. 发送
                page.keyboard.press('Enter')
                
                # C. 等待回答生成
                print(">>> 等待回答...")
                last_text = ""
                stable_start_time = time.time()
                time.sleep(2) # 给它一点反应时间

                while True:
                    try:
                        # 获取所有消息气泡
                        # 这是一个通用策略：找所有包含大量文字的 div，取最后一个
                        # 豆包的消息气泡通常包含特定结构，但 class 经常变
                        # 我们尝试抓取 conversation container 里的最后一条
                        
                        # 尝试定位所有气泡
                        msgs = page.query_selector_all('div[data-testid="message-card-content"]')
                        # 如果上面的找不到，尝试找所有 text-base 类的 div
                        if not msgs:
                            msgs = page.query_selector_all('.msg-content')
                        
                        if not msgs:
                            time.sleep(1)
                            continue

                        current_text = msgs[-1].inner_text()
                    except:
                        current_text = last_text

                    # 检查是否还在生成 (字数在增加)
                    if current_text != last_text and len(current_text) > len(last_text):
                        last_text = current_text
                        stable_start_time = time.time()
                        print(f"\r>>> 生成中... {len(current_text)} 字", end="")
                    else:
                        # 如果由内容且 4秒内字数没变，认为结束
                        if time.time() - stable_start_time > 4 and len(current_text) > 2:
                            print(f"\n>>> 回答获取完成！")
                            break
                    
                    # 超时保护 (120秒)
                    if time.time() - stable_start_time > 120:
                        print("\n>>> 等待超时，跳过此题。")
                        break
                        
                    time.sleep(1)

                # D. 存盘
                entry = {"id": index+1, "question": q, "answer": last_text}
                
                # 读取旧数据追加
                data_list = []
                if os.path.exists(OUTPUT_FILE):
                    try:
                        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                            data_list = json.load(f)
                    except: pass
                
                data_list.append(entry)
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data_list, f, ensure_ascii=False, indent=2)

                # E. 休息
                sleep_time = random.randint(15, 25)
                print(f">>> 模拟阅读，休息 {sleep_time} 秒...")
                time.sleep(sleep_time)

            except Exception as e:
                print(f"处理出错: {e}")
                # 尝试刷新页面恢复环境
                try:
                    page.reload()
                    page.wait_for_selector(final_selector, timeout=10000)
                except:
                    pass
                continue

        print("\n全部完成！")
        # 此时再关闭浏览器
        browser.close()

if __name__ == "__main__":
    run_automation()