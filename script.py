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
# yfinance의 FX Ticker는 '외화KRW=X' 형식을 사용합니다.
FX_TICKERS = {
    "USD": "KRW=X",        # YF Ticker for USD/KRW (1 USD = X KRW)
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
        
        # 1. 가격 및 거래량 데이터 (히스토리)
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
        high_52w = info.get('fiftyTwoWeekHigh', 0.0)
        low_52w = info.get('fiftyTwoWeekLow', 0.0)
        
        # 3. 거래량
        current_volume = volumes.iloc[-1]

        # 변동률 계산
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
        # 넉넉하게 7일 데이터를 가져와서 5일 전 Rate까지 계산
        fx_data = yf.download(symbol, period=f"{days+2}d", interval="1d")
        
        close_rates = fx_data.get('Close').dropna()
        
        if close_rates.empty or len(close_rates) < 2:
            return None, "데이터 부족 또는 조회된 거래일이 2일 미만"
            
        current_rate = close_rates.iloc[-1]
        yesterday_rate = close_rates.iloc[-2]
        
        week_ago_rate = None
        if len(close_rates) >= days + 1:
            week_ago_rate = close_rates.iloc[-days - 1] 

        # 변동률 계산
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
    
    # 주식/지수 메시지 포맷 함수 정의
    def format_stock_message(name, symbol, data, currency_symbol, is_kr_stock=False):
        
        # 한국 주식인 경우 값 자체를 정수로 변환하여 포맷을 : ,d로 설정합니다.
        if is_kr_stock:
            price = round(data['price'])
            low_52w = round(data['low_52w'])
            high_52w = round(data['high_52w'])
            # 정수형에 대한 쉼표 포맷
            price_format = ":,d" 
        else:
            price = data['price']
            low_52w = data['low_52w']
            high_52w = data['high_52w']
            # 미국 주식은 소수점 두 자리 포맷
            price_format = ":,.2f" 
        
        # f-string 포맷 문자열을 format() 함수를 사용하여 동적으로 구성
        price_str = format(price, price_format)
        low_52w_str = format(low_52w, price_format)
        high_52w_str = format(high_52w, price_format)

        result = (
            f"• *{name}* ({symbol}): {currency_symbol}{price_str}\n"
            f"  > *변동률:* 일:{data['daily_change']:+.2f}%, 주:{data['weekly_change']:+.2f}%\n"
            f"  > *거래량:* {data['volume']:,}주 | *52주 범위:* {currency_symbol}{low_52w_str} ~ {currency_symbol}{high_52w_str}"
        )
        return result

    # 1. 국내 주식 및 지수 조회
    kr_results = ["\n*🇰🇷 국내 주식 및 지수*"]
    for name, symbol in KR_TICKERS.items():
        data, error = get_price_data(symbol)
        if data:
            # is_kr_stock=True 설정
            kr_results.append(format_stock_message(name, symbol, data, "₩", is_kr_stock=True))
        else:
            kr_results.append(f"• {name} ({symbol}): [조회 실패] - {error}")
    message_parts.append("\n".join(kr_results))
    
    # 2. 미국 주식 및 지수 조회
    us_results = ["\n*🇺🇸 미국 주식 및 지수*"]
    for name, symbol in US_TICKERS.items():
        data, error = get_price_data(symbol, days=5)
        if data:
            # is_kr_stock=False(기본값)이므로 소수점 두 자리 포맷 적용
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
             # 환율은 소수점 2자리까지 표시 (1400.50원)
             fx_list.append(
                f"• *{target}*: {data['rate']:,.2f}원 (일:{data['daily_change']:+.2f}%, 주:{data['weekly_change']:+.2f}%)"
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