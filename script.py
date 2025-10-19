import os
from datetime import datetime
import yfinance as yf # yfinance 추가 (requirements.txt에 yfinance 있어야 함)
import requests # 환율 API를 위해 req

# -------------------------------
# 환경변수에서 Slack Webhook URL 가져오기
# -------------------------------
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

if not SLACK_WEBHOOK_URL:
    raise ValueError("Slack Webhook URL이 환경변수에 설정되어 있지 않습니다.")

# -------------------------------
# 주가 정보 가져오기
# -------------------------------
def get_stock_price(symbol):
    """yfinance 라이브러리를 사용하여 주가 가져오기"""
    try:
        ticker = yf.Ticker(symbol)
        # 1일(1d) 간격의 데이터에서 종가(Close)를 가져옴
        price_data = ticker.history(period="1d")
        
        if price_data.empty:
            raise ValueError(f"{symbol} 주식 가격 정보를 가져올 수 없습니다. (데이터 없음)")
            
        price = price_data["Close"].iloc[-1]
        return round(float(price), 2)
        
    except Exception as e:
        # yfinance 내부에서 발생할 수 있는 모든 오류 처리
        raise ValueError(f"{symbol} 주식 정보 조회 실패 (yfinance 오류): {e}")

# -------------------------------
# 환율 정보 가져오기
# -------------------------------
def get_exchange_rate(base, target):
    # API URL을 frankfurter로 변경
    url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"{base}->{target} 환율 API 요청 실패: {e}")
    
    try:
        data = response.json()
    except ValueError:
        raise ValueError(f"{base}->{target} 환율 API 응답 JSON 파싱 실패: {response.text}")
    
    rates = data.get("rates")
    if not rates or target not in rates:
        raise ValueError(f"{base}->{target} 환율 정보를 가져올 수 없습니다: {data}")
    
    # frankfurter API의 응답 구조는 rates 아래에 타겟 통화가 바로 있습니다.
    return round(rates[target], 2)

# -------------------------------
# Slack 메시지 전송
# -------------------------------
def send_to_slack(message):
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Slack 메시지 전송 실패: {e}")

# -------------------------------
# 메인 실행
# -------------------------------
def main():
    try:
        # 예시: 카카오 주식과 USD/KRW 환율
        kakao_price = get_stock_price("035720.KQ")  # 카카오 주식
        usdkrw = get_exchange_rate("USD", "KRW")
        
        # 메시지 생성
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{now}] 카카오 주가: {kakao_price}원, USD/KRW 환율: {usdkrw}"
        
        # Slack 전송
        send_to_slack(message)
        print("Slack 메시지 전송 성공:", message)
        
    except Exception as e:
        error_message = f"스크립트 실행 중 오류 발생: {e}"
        print(error_message)
        # 오류도 Slack에 전송 (가능하면)
        try:
            send_to_slack(error_message)
        except:
            pass

if __name__ == "__main__":
    main()
