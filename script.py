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

# 국내 주식 및 지수
KR_TICKERS = {
    "삼성전자": "005930.KS", 
    "LG디스플레이": "034220.KS",
    "코스피": "^KS11",
    "코스닥": "^KQ11",
}

# 미국 주식, 지수 및 ETF
US_TICKERS = {
    "S&P 500": "^GSPC",
    "나스닥 종합": "^IXIC",
    "다우존스": "^DJI",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "엔비디아": "NVDA",
    "테슬라": "TSLA",
    "QQQ (나스닥100)": "QQQ",
}

# 주요국 환율 (기준 통화: 원화 KRW)
FX_TICKERS = [
    "USD", "JPY", "EUR", "GBP", "CNY", "CAD", "AUD", "CHF", "SGD", 
    "HKD", "NZD", "SEK", "NOK", "MXN", "BRL", "INR", "TRY", "PLN"
]

# -------------------------------
# 주가/지수 정보 가져오기 (변동률, 52주, 거래량 포함) - 수정됨
# -------------------------------
def get_price_data(symbol, days=5):
    """yfinance를 사용하여 종가, 변동률, 52주 범위, 거래량 계산"""
    try:
        ticker = yf.Ticker(symbol)
        
        # 1. 가격 및 거래량 데이터 (히스토리)
        # 'progress=False' 인자 제거!
        price_data = ticker.history(period=f"{days+2}d", interval="1d")
        close_prices = price_data.get('Close').dropna()
        volumes = price_data.get('Volume').dropna()
        
        # 데이터 유효성 검사 (최소 2일 데이터 필요)
        if close_prices.empty or len(close_prices) < 2:
            return None, "데이터 부족 또는 조회된 거래일이 2일 미만"
            
        current_price = close_prices.iloc[-1]
        yesterday_price = close_prices.iloc[-2]
        
        # 1주일 변동률을 위한 5거래일 전 종가
        week_ago_price = None
        if len(close_prices) >= days + 1:
            week_ago_price = close_prices.iloc[-days - 1] 

        # 2. 52주 최고/최저가 데이터 (info)
        info = ticker.info
        # 지수(Index)의 경우 52주 정보가 없을 수 있으므로 기본값 0으로 설정
        high_52w = info.get('fiftyTwoWeekHigh', 0)
        low_52w = info.get('fiftyTwoWeekLow', 0)
        
        # 3. 거래량
        current_volume = volumes.iloc[-1]

        # 변동률 계산
        daily_change = (current_price - yesterday_price) / yesterday_price * 100
        weekly_change = (current_price - week_ago_price) / week_ago_price * 100 if week_ago_price is not None and week_ago_price != 0 else 0.0

        return {
            "price": round(float(current_price), 2),
            "daily_change": round(daily_change, 2),
            "weekly_change": round(weekly_change, 2),
            "volume": int(current_volume),
            "high_52w": round(float(high_52w), 2),
            "low_52w": round(float(low_52w), 2),
        }, None
        
    except Exception as e:
        return None, f"조회 실패 (yfinance): {e}"

# -------------------------------
# 환율 정보 가져오기 (기준 통화: KRW)
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
        return None 
    
    return round(rates[target], 5) # 환율은 소수점 5자리까지 표시

# -------------------------------
# Slack 메시지 전송
# -------------------------------
def send_to_slack(message):
    payload = {"text": message}
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
    
    # 메시지 포맷 함수 정의 (재사용을 위해)
    def format_stock_message(name, symbol, data, currency_symbol):
        # 52주 최고/최저가와 거래량을 포함하여 상세 포매팅
        result = (
            f"• *{name}* ({symbol}): {currency_symbol}{data['price']:,.2f}\n"
            f"  > *변동률:* 일:{data['daily_change']:+.2f}%, 주:{data['weekly_change']:+.2f}%\n"
            f"  > *거래량:* {data['volume']:,}주 | *52주 범위:* {currency_symbol}{data['low_52w']:,.2f} ~ {currency_symbol}{data['high_52w']:,.2f}"
        )
        return result

    # 1. 국내 주식 및 지수 조회
    kr_results = ["\n*🇰🇷 국내 주식 및 지수*"]
    for name, symbol in KR_TICKERS.items():
        data, error = get_price_data(symbol)
        if data:
            kr_results.append(format_stock_message(name, symbol, data, "₩"))
        else:
            kr_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(kr_results))
    
    # 2. 미국 주식 및 지수 조회
    us_results = ["\n*🇺🇸 미국 주식 및 지수*"]
    for name, symbol in US_TICKERS.items():
        data, error = get_price_data(symbol, days=5)
        if data:
            us_results.append(format_stock_message(name, symbol, data, "$"))
        else:
            us_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(us_results))

    # 3. 환율 정보 조회 (기준: KRW)
    fx_results = ["\n*🌍 주요국 환율 (원화 KRW 기준)*"]
    fx_list = []
    
    for target in FX_TICKERS:
        rate = get_exchange_rate("KRW", target)
        
        if rate:
             # 결과 포맷: KRW/USD: 0.0007 (1원당 달러 가치)
             fx_list.append(f"KRW/{target}: {rate:,.5f}") 
        else:
             fx_list.append(f"KRW/{target}: 조회 불가")
             
    fx_results.append("\n".join(fx_list))
    message_parts.append("\n".join(fx_results))

    # 최종 Slack 메시지 구성
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"🚀 *일일 주식/환율 자동 보고서* ({now}) 🚀\n"
    final_message = header + "\n".join(message_parts)

    try:
        # Slack 전송
        send_to_slack(final_message)
        print("Slack 메시지 전송 성공 (상세 리포트 포함)")
        
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