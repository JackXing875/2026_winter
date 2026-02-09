import pandas as pd
import json
import time
import random
from playwright.sync_api import sync_playwright

# 配置部分
CSV_PATH = 'questions.csv'
OUTPUT_JSON = 'doubao_results.json'
DOUBAO_URL = 'https://www.doubao.com/chat/' # 假设的URL，请确认实际URL

def run():
    # 1. 读取 CSV
    df = pd.read_csv(CSV_PATH)
    questions = df.iloc[:, 0].tolist() # 假设问题在第一列
    
    results = []

    with sync_playwright() as p:
        # 2. 启动浏览器 (headless=False 才能看到界面并手动登录)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # 3. 打开网页并等待人工登录
        page.goto(DOUBAO_URL)
        print(">>> 请在 40 秒内完成扫码/登录操作...")
        time.sleep(40) # 给你留出登录时间
        
        print(">>> 开始自动化提问...")

        for idx, question in enumerate(questions):
            print(f"正在处理第 {idx+1}/{len(questions)} 个问题: {question[:10]}...")
            
            try:
                # A. 定位输入框并输入 (Selector 需要你自己按 F12 获取)
                # 示例 Selector，请务必在浏览器控制台验证
                input_selector = 'div[contenteditable="true"]' # 常见的富文本输入框定位
                page.wait_for_selector(input_selector, timeout=10000)
                page.fill(input_selector, question)
                
                # B. 点击发送
                send_button_selector = '#flow-end-msg-send' # 示例ID
                page.click(send_button_selector)
                
                # C. 等待回答完成
                # 策略：等待"发送"按钮再次出现，或者等待"停止生成"按钮消失
                # 这里假设生成中会有一个特定的 loading 状态，生成完消失
                # 更通用的笨办法：每秒检查一次最后一个回答的内容长度，如果5秒没变，就认为完了
                
                last_text = ""
                stable_count = 0
                
                # 循环检测回答是否稳定
                while True:
                    time.sleep(2) 
                    # 获取所有回答气泡
                    answers = page.query_selector_all('.msg-content') # 假设回答的class是这个
                    if not answers:
                        continue
                        
                    current_text = answers[-1].inner_text()
                    
                    if current_text == last_text and len(current_text) > 5:
                        stable_count += 1
                    else:
                        stable_count = 0
                        last_text = current_text
                    
                    # 连续 3 次检查（6秒）文本没变，且不是空文本，认为生成结束
                    if stable_count >= 3:
                        break
                    
                    # 超时保护（比如一个问题卡了2分钟）
                    # ... (可添加)

                # D. 存 JSON (实时追加，防止脚本崩溃)
                entry = {"id": idx, "question": question, "answer": last_text}
                results.append(entry)
                
                # 写入文件
                with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                
                # E. 模拟人类休眠
                sleep_time = random.randint(20, 40)
                print(f"回答获取成功，休眠 {sleep_time} 秒...")
                time.sleep(sleep_time)

            except Exception as e:
                print(f"处理问题 '{question}' 时出错: {e}")
                # 也可以选择记录错误后 continue 继续下一个

        browser.close()
        print(">>> 全部完成！")

if __name__ == '__main__':
    run()