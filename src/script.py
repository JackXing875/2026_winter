import time
import random
import json
import pandas as pd
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
CSV_FILE = '/home/schrieffer/2026_winter/data/questions.csv'      # 问题文件路径
OUTPUT_FILE = 'doubao_answers.json' # 结果保存路径
DOUBAO_URL = 'https://www.doubao.com/chat/'

# 模拟人类的打字速度（字符间隔秒数）
TYPE_DELAY_MIN = 0.05
TYPE_DELAY_MAX = 0.15

# 回答稳定判定时间（秒）：如果 AI 5秒都不吐新字，认为回答结束
STABLE_WAIT_TIME = 5 
# ----------------

def run_automation():
    # 1. 读取问题
    try:
        df = pd.read_csv(CSV_FILE)
        questions = df['question'].tolist() # 确保 CSV 表头有一列叫 question
    except Exception as e:
        print(f"读取 CSV 失败: {e}")
        return

    results = []

    with sync_playwright() as p:
        # 启动浏览器 (headless=False 表示有界面，方便扫码)
        browser = p.chromium.launch(headless=False, args=['--start-maximized'])
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        # 2. 打开网页并人工登录
        print(">>> 正在打开豆包...")
        page.goto(DOUBAO_URL)
        
        print("\n" + "="*50)
        print("!!! 请在浏览器中手动完成扫码/手机号登录 !!!")
        print("!!! 登录成功并进入聊天界面后，请按回车键继续脚本 !!!")
        print("="*50 + "\n")
        input(">>> 按回车继续...")

        # 3. 开始循环提问
        # 定位输入框：豆包通常使用 contenteditable 的 div
        # 选择器策略：找到属性为 contenteditable="true" 的 div
        input_selector = 'div[contenteditable="true"]' 

        for index, q in enumerate(questions):
            print(f"\n[{index+1}/{len(questions)}] 正在提问: {q}")
            
            try:
                # --- A. 输入问题 ---
                page.click(input_selector)
                # 模拟打字（防风控）
                page.keyboard.type(q, delay=random.randint(50, 100)) 
                time.sleep(1)
                
                # --- B. 发送问题 ---
                page.keyboard.press('Enter')
                print(">>> 问题已发送，等待回答生成...")
                
                # --- C. 等待回答完成 (基于文本长度稳定性检测) ---
                # 这是一个“笨”但通用的方法，不依赖特定的"停止生成"按钮 ID
                last_text = ""
                stable_start_time = time.time()
                
                # 给 AI 一点反应时间，防止刚发出去就检测
                time.sleep(3) 

                while True:
                    # 获取所有 AI 的回答气泡
                    # 注意：你需要根据实际情况微调这个 Selector
                    # 豆包目前的回答气泡通常包含 markdown 类名或特定的结构
                    # 下面的 selector 尝试获取所有非用户的消息气泡
                    try:
                        # 这是一个比较通用的定位策略，定位最后一个消息内容
                        # 如果脚本报错找不到元素，请在浏览器按F12查看回答气泡的class
                        msgs = page.query_selector_all('div[data-testid="message-card-content"]') 
                        
                        if not msgs:
                            # 可能是页面结构变了，或者还没渲染出来
                            time.sleep(1)
                            continue

                        # 获取最后一个气泡的文本
                        current_content_el = msgs[-1]
                        current_text = current_content_el.inner_text()
                    except Exception as e:
                        print(f"获取回答元素出错 (生成中...): {e}")
                        current_text = last_text # 保持不变继续等

                    # 检查文本是否变化
                    if current_text != last_text:
                        last_text = current_text
                        stable_start_time = time.time() # 重置计时器
                        print(f"\r>>> 生成中... 当前字数: {len(current_text)}", end="")
                    else:
                        # 文本没变，检查持续了多久
                        elapsed = time.time() - stable_start_time
                        if elapsed > STABLE_WAIT_TIME and len(current_text) > 0:
                            print(f"\n>>> 回答生成完毕 (长度: {len(current_text)})")
                            break
                    
                    # 避免死循环，设置单题最大超时 (例如 180秒)
                    # if time.time() - start_time > 180: break
                    
                    time.sleep(1)

                # --- D. 保存结果 ---
                record = {
                    "id": index + 1,
                    "question": q,
                    "answer": last_text,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                results.append(record)
                
                # 实时写入文件（追加模式或重写模式），防止中途崩溃数据丢失
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

                # --- E. 模拟人类思考/阅读 (休眠) ---
                sleep_sec = random.randint(20, 40)
                print(f">>> 模拟阅读，休息 {sleep_sec} 秒...")
                time.sleep(sleep_sec)

            except Exception as e:
                print(f"!!! 处理第 {index+1} 个问题时出错: {e}")
                # 截图保存错误现场
                page.screenshot(path=f"error_{index}.png")
                continue

        print("\n所有问题处理完毕！")
        browser.close()

if __name__ == "__main__":
    run_automation()