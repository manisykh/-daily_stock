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

# 주요국 환율 (기준: 1 외화당 KRW)
FX_TICKERS = {
    "USD": "KRW=X",        
    "JPY": "JPYKRW=X",
    "EUR": "EURKRW=X",
    "GBP": "GBPKRW=X",
    "CNY": "CNYKRW=X",
    "CAD": "CADKRW=X",
    "AUD": "AUDKRW=X",
    "CHF": "CHFKRW=X",
    "SGD": "SGD/KRW=X",
    "HKD": "HKDKRW=X",
    "NZD": "NZD/KRW=X",
    "SEK": "SEKKRW=X",
    "NOK": "NOKKRW=X",
    "MXN": "MXNKRW=X",
    "BRL": "BRLKRW=X",
    "INR": "INRKRW=X",
    "TRY": "TRYKRW=X",
    "PLN": "PLNKRW=X",
}

# -------------------------------
# 주가/지수 정보 가져오기 (변동률, 52주, 거래량 포함)
# -------------------------------
def get_price_data(symbol, days=5):
    """yfinance를 사용하여 종가, 변동률, 52주 범위, 거래량 계산"""
    try:
        ticker = yf.Ticker(symbol)
        
        price_data = ticker.history(period=f"{days+2}d", interval="1d")
        close_prices = price_data.get('Close').dropna()
        volumes = price_data.get('Volume').dropna()
        
        if close_prices.empty or len(close_prices) < 2:
            return None, "데이터 부족 또는 조회된 거래일이 2일 미만"
            
        current_price = close_prices.iloc[-1]
        yesterday_price = close_prices.iloc[-2]
        
        week_ago_price = None
        if len(close_prices) >= days + 1:
            week_ago_price = close_prices.iloc[-days - 1] 

        info = ticker.info
        high_52w = info.get('fiftyTwoWeekHigh', 0.0)
        low_52w = info.get('fiftyTwoWeekLow', 0.0)
        
        current_volume = volumes.iloc[-1]

        daily_change = (current_price - yesterday_price) / yesterday_price * 100
        weekly_change = (current_price - week_ago_price) / week_ago_price * 100 if week_ago_price is not None and week_ago_price != 0 else 0.0

        return {
            "price": float(current_price),
            "low_52w": float(low_52w),
            "high_52w": float(high_52w),
            "daily_change": round(daily_change, 2),
            "weekly_change": round(weekly_change, 2),
            "volume": int(current_volume),
        }, None
        
    except Exception as e:
        return None, f"조회 실패 (yfinance): {e}"

# -------------------------------
# 환율 히스토리 및 변동률 정보 가져오기 (yfinance 사용)
# -------------------------------
def get_fx_data(symbol, days=5):
    """yfinance를 사용하여 FX rate의 히스토리 데이터를 가져와 변동률을 계산"""
    try:
        fx_data = yf.download(symbol, period=f"{days+2}d", interval="1d")
        
        close_rates = fx_data.get('Close').dropna()
        
        if close_rates.empty or len(close_rates) < 2:
            return None, "데이터 부족 또는 조회된 거래일이 2일 미만"
            
        current_rate = close_rates.iloc[-1]
        yesterday_rate = close_rates.iloc[-2]
        
        week_ago_rate = None
        if len(close_rates) >= days + 1:
            week_ago_rate = close_rates.iloc[-days - 1] 

        daily_change = (current_rate - yesterday_rate) / yesterday_rate * 100
        weekly_change = (current_rate - week_ago_rate) / week_ago_rate * 100 if week_ago_rate is not None and week_ago_rate != 0 else 0.0

        return {
            "rate": round(float(current_rate), 2), 
            "daily_change": round(daily_change, 2),
            "weekly_change": round(weekly_change, 2),
        }, None
        
    except Exception as e:
        return None, f"조회 실패 (yfinance FX): {e}"

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
    
    # 변동률 포맷 함수 (이모지 처리)
    def format_change(change_rate):
        """변동률에 따라 이모지 및 마크다운을 적용하여 포맷합니다."""
        if change_rate > 0:
            return f"*⬆️ +{change_rate:.2f}%*" 
        elif change_rate < 0:
            return f"*⬇️ {change_rate:+.2f}%*" 
        else:
            return f"↔️ {change_rate:+.2f}%"

    # 주식/지수 메시지 포맷 함수 정의
    def format_stock_message(name, symbol, data, currency_symbol, is_kr_stock=False):
        
        if is_kr_stock:
            # 쉼표 포맷만 사용하기 위해 정수형으로 변환
            price = round(data['price'])
            low_52w = round(data['low_52w'])
            high_52w = round(data['high_52w'])
            
            # 💡 수정된 부분: f-string을 사용하여 정수형의 쉼표 포맷 처리
            price_str = f"{price:,}"
            low_52w_str = f"{low_52w:,}"
            high_52w_str = f"{high_52w:,}"
            
        else:
            price = data['price']
            low_52w = data['low_52w']
            high_52w = data['high_52w']
            
            # 미국 주식은 소수점 두 자리 포맷도 f-string으로 처리
            price_str = f"{price:,.2f}"
            low_52w_str = f"{low_52w:,.2f}"
            high_52w_str = f"{high_52w:,.2f}"

        daily_change_str = format_change(data['daily_change'])
        weekly_change_str = format_change(data['weekly_change'])

        result = (
            f"• *{name}* ({symbol}): {currency_symbol}{price_str}\n"
            f"  > *변동률:* 일:{daily_change_str}, 주:{weekly_change_str}\n"
            f"  > *거래량:* {data['volume']:,}주 | *52주 범위:* {currency_symbol}{low_52w_str} ~ {currency_symbol}{high_52w_str}"
        )
        return result

    # 1. 국내 주식 및 지수 조회
    kr_results = ["\n*🇰🇷 국내 주식 및 지수*"]
    for name, symbol in KR_TICKERS.items():
        data, error = get_price_data(symbol)
        if data:
            kr_results.append(format_stock_message(name, symbol, data, "₩", is_kr_stock=True))
        else:
            kr_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(kr_results))
    
    # 2. 미국 주식 및 지수 조회
    us_results = ["\n*🇺🇸 미국 주식 및 지수*"]
    for name, symbol in US_TICKERS.items():
        data, error = get_price_data(symbol, days=5)
        if data:
            us_results.append(format_stock_message(name, symbol, data, "$", is_kr_stock=False))
        else:
            us_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(us_results))

    # 3. 환율 정보 조회 (기준: 1 외화당 KRW)
    fx_results = ["\n*🌍 주요국 환율 (1 외화당 KRW)*"]
    fx_list = []
    
    for target, symbol in FX_TICKERS.items():
        data, error = get_fx_data(symbol)
        
        if data:
             daily_change_str = format_change(data['daily_change'])
             weekly_change_str = format_change(data['weekly_change'])
             
             # 환율은 소수점 2자리까지 표시
             fx_list.append(
                f"• *{target}*: {data['rate']:,.2f}원 (일:{daily_change_str}, 주:{weekly_change_str})"
             )
        else:
             fx_list.append(f"• *{target}*: [조회 실패] - {error}")
             
    fx_results.extend(fx_list)
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