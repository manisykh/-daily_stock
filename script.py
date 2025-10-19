import os
from datetime import datetime
import yfinance as yf
import requests

# -------------------------------
# 환경변수에서 Slack Webhook URL 가져오기
# -------------------------------
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL") 

if not SLACK_WEBHOOK_URL:
    raise ValueError("Slack Webhook URL이 환경변수에 설정되어 있지 않습니다.")

# -------------------------------
# 조회 대상 리스트 정의
# -------------------------------

# 국내 주식 및 지수 (KS: 코스피, KQ: 코스닥, ^KS11: 코스피 지수, ^KQ11: 코스닥 지수)
KR_TICKERS = {
    "삼성전자": "005930.KS", 
    "LG디스플레이": "034220.KS",
    "코스피": "^KS11",
    "코스닥": "^KQ11",
}

# 미국 주식, 지수 및 ETF (yfinance 심볼 사용)
US_TICKERS = {
    "S&P 500": "^GSPC",
    "나스닥 종합": "^IXIC",
    "다우존스": "^DJI",
    "VIX": "^VIX",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "아마존": "AMZN",
    "엔비디아": "NVDA",
    "테슬라": "TSLA",
    "SOXX (반도체)": "SOXX",
    "QQQ (나스닥100)": "QQQ",
}
# 편의상 모든 종목을 담기 어려워 핵심 종목 및 요청 종목만 일부 반영했습니다.

# 주요국 환율 (기준 통화: USD)
FX_TICKERS = [
    "KRW", "JPY", "EUR", "GBP", "CNY", "CAD", "AUD", "CHF", "SGD", 
    "HKD", "NZD", "SEK", "NOK", "MXN", "BRL", "INR", "TRY", "PLN"
]

# -------------------------------
# 주가/지수 정보 가져오기 (변동률 계산 포함)
# -------------------------------
def get_price_data(symbol, days=5):
    """yfinance를 사용하여 종가, 일간/주간 변동률을 계산"""
    try:
        # 넉넉하게 7거래일 데이터를 가져와서 5일 전 종가까지 계산
        price_data = yf.download(symbol, period=f"{days+2}d", interval="1d", progress=False)
        
        if price_data.empty or len(price_data) < 2:
            return None, "데이터 부족"
            
        close_prices = price_data['Close'].dropna()
        
        # 오늘 종가 (마지막 데이터)
        current_price = close_prices.iloc[-1]
        
        # 어제 종가 (마지막에서 두 번째 데이터)
        yesterday_price = close_prices.iloc[-2]
        
        # 1주일 전 종가 (5거래일 전, 데이터가 충분할 경우)
        if len(close_prices) >= days + 1:
            week_ago_price = close_prices.iloc[-days - 1] 
        else:
            week_ago_price = None

        # 일간 변동률 계산
        daily_change = (current_price - yesterday_price) / yesterday_price * 100
        
        # 1주일 변동률 계산
        weekly_change = (current_price - week_ago_price) / week_ago_price * 100 if week_ago_price else 0.0

        return {
            "price": round(float(current_price), 2),
            "daily_change": round(daily_change, 2),
            "weekly_change": round(weekly_change, 2),
        }, None
        
    except Exception as e:
        return None, f"조회 실패 (yfinance): {e}"

# -------------------------------
# 환율 정보 가져오기 (기존 코드 유지)
# -------------------------------
def get_exchange_rate(base, target):
    url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise ValueError(f"{base}->{target} 환율 API 요청 실패: {e}")
    except ValueError:
        raise ValueError(f"{base}->{target} 환율 API 응답 JSON 파싱 실패")
    
    rates = data.get("rates")
    if not rates or target not in rates:
        return None # 데이터 없을 경우 None 반환
    
    return round(rates[target], 2)

# -------------------------------
# Slack 메시지 전송 (기존 코드 유지)
# -------------------------------
def send_to_slack(message):
    payload = {"text": message}
    # SLACK_WEBHOOK_URL이 전역 변수로 이미 검증되었음을 전제합니다.
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        if response.status_code != 200:
             raise requests.RequestException(f"Slack 서버 응답 오류: HTTP {response.status_code}")
             
    except requests.RequestException as e:
        raise ValueError(f"Slack 메시지 전송 실패: {e}")

# -------------------------------
# 메인 실행
# -------------------------------
def main():
    message_parts = []
    
    # 1. 국내 주식 및 지수 조회
    kr_results = ["\n*🇰🇷 국내 주식 및 지수*"]
    for name, symbol in KR_TICKERS.items():
        data, error = get_price_data(symbol)
        if data:
            # ⭐ 140번째 줄 오류 수정 예상 위치 ⭐
            # f-string 포매팅을 확인했습니다. (':,.2f', ':+ .2f%')
            result = f"• {name} ({symbol}): {data['price']:,.2f}원 (일:{data['daily_change']:+.2f}%, 주:{data['weekly_change']:+.2f}%)"
            kr_results.append(result)
        else:
            kr_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(kr_results))
    
    # 2. 미국 주식 및 지수 조회
    us_results = ["\n*🇺🇸 미국 주식 및 지수*"]
    for name, symbol in US_TICKERS.items():
        data, error = get_price_data(symbol, days=5)
        if data:
            result = f"• {name} ({symbol}): ${data['price']:,.2f} (일:{data['daily_change']:+.2f}%, 주:{data['weekly_change']:+.2f}%)"
            us_results.append(result)
        else:
            us_results.append(f"• {name} ({symbol}): ${{조회 실패}} - {error}")
    message_parts.append("\n".join(us_results))

    # 3. 환율 정보 조회 (기준: USD)
    fx_results = ["\n*🌍 주요국 환율 (USD 기준)*"]
    fx_list = []
    for target in FX_TICKERS:
        # USD를 기준으로 KRW 외 통화의 환율을 조회합니다.
        rate = get_exchange_rate("USD", target)
        if rate:
             fx_list.append(f"USD/{target}: {rate:,.2f}")
        else:
             fx_list.append(f"USD/{target}: 조회 불가")
             
    fx_results.append(" | ".join(fx_list))
    message_parts.append("\n".join(fx_results))

    # 최종 Slack 메시지 구성
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"🚀 *일일 주식/환율 자동 보고서* ({now})\n"
    final_message = header + "\n".join(message_parts)

    try:
        # Slack 전송
        send_to_slack(final_message)
        print("Slack 메시지 전송 성공 (상세 리포트)")
        
    except Exception as e:
        error_message = f"스크립트 실행 중 오류 발생: {e}"
        print(f"FATAL: {error_message}")
        
        # 오류 메시지를 Slack에 다시 전송 시도
        try:
            send_to_slack(error_message)
        except ValueError as slack_e:
            print(f"FATAL: 오류 메시지 Slack 재전송 실패. Webhook 오류일 수 있음: {slack_e}")
            pass

if __name__ == "__main__":
    main()