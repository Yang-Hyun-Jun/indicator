
import requests, json, os
import pandas as pd
import argparse
import warnings
import numpy as np
import tqdm
import datetime
import multiprocessing
import time
import requests
from dateutil.relativedelta import relativedelta

warnings.filterwarnings("ignore")

CMC_API_KEY = "d9b8fcb8-474b-4bc0-8704-d99bcd1975e0"


class DataLabel:
    close = "close"
    high = "high"
    low = "low"
    open = "open"
    volume = "volume"
    market_cap = "market_cap"
    
    

class CoinMarketCap:
    def __init__(self, api_key) -> None:
        # auth Bearer
        self.api_key = api_key
        self.BASE_URL = "https://pro-api.coinmarketcap.com/"
        self.headers = {"X-CMC_PRO_API_KEY": f"{self.api_key}", 'Accepts': 'application/json'}

        self.MAX_DATACNT = 365 * 6

    def get_all_listings(self):
        url = self.BASE_URL + "v1/cryptocurrency/listings/latest"
        response = requests.get(url, headers=self.headers, params={"limit": 5000})
        return json.loads(response.content)["data"]
    
    def get_metadata(self, symbols:list):
        url = self.BASE_URL + "v2/cryptocurrency/info"
        response = requests.get(url, headers=self.headers, params={"symbol": ",".join(symbols)})
        raw = json.loads(response.content)
        return raw["data"]
    
    def get_ohlcv_realtime(self, symbol):
        url = self.BASE_URL + "v2/cryptocurrency/ohlcv/latest"
        response = requests.get(
            url,
            headers=self.headers,
            params={
                "symbol": ",".join(symbol),
            },
        )

        raw = json.loads(response.content)["data"]
        return raw

    def get_ohlcv_historical(self, symbol, start, end=None):
        #try:
        url = self.BASE_URL + "v2/cryptocurrency/ohlcv/historical"
        response = requests.get(
            url,
            headers=self.headers,
            params={
                "symbol": symbol,
                "time_start": start,
                "time_end": end,
                "count": self.MAX_DATACNT,
                "interval": "1d",
                
            },
        )
        raw = response.content
        return json.loads(raw)["data"][symbol][0]["quotes"]
        # except Exception as e:
        #     print(f"[ERROR] on symbol {symbol} {e}... RAW: {raw} retrying")
        #     time.sleep(10)
        #     return self.get_ohlcv_historical(symbol, start, end)
        

def download_coinmarketcap(symbols, save_path="./data/coinmarketcap"):
    coinmarketcap = CoinMarketCap(CMC_API_KEY)
    
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    project_infos  = coinmarketcap.get_metadata(symbols)

    with open(os.path.join(save_path, "metadata.json"), "w") as f:
        json.dump(project_infos, f)

    
    data_store = pd.HDFStore(os.path.join(save_path, "data.hdf5"))

    for symbol in tqdm.tqdm(symbols, desc="download"):
        if not symbol in project_infos.keys():
            print("skipping unknown symbol", symbol)
            continue

        if not f"/_{symbol}" in data_store.keys():
            start_date = datetime.datetime.now() - relativedelta(years=5)
            start_date = start_date.strftime("%Y-%m-%d")

            print("Downloading", symbol, start_date)
        else:
            start_date = data_store["_" + symbol].index[-1]
            start_date = start_date.strftime("%Y-%m-%d")
        try:
            data = coinmarketcap.get_ohlcv_historical(symbol, start_date)
        except Exception as e:
            print(f"[ERROR] on symbol {symbol} {e}... skipping")
            continue
        data = [data["quote"]["USD"] for data in data]

        if data == []:
            continue

        data = pd.DataFrame(data)

        data["timestamp"] = pd.to_datetime(data["timestamp"])
        data.drop_duplicates("timestamp", inplace=True)
        data.set_index("timestamp", inplace=True)
        data.sort_index(inplace=True)

        if symbol in data_store.keys():
            data_store["_" + symbol] = pd.concat([data_store[symbol], data])
        else:
            data_store["_" + symbol] = data
    
    data_store.close()


def convert_data(data):
    data["timestamp"] = data.index.strftime("%Y-%m-%d")
    data.index = pd.to_datetime(
        [d[:10] for d in data["timestamp"].to_list()], format="%Y-%m-%d"
    )
    return data.sort_values("timestamp")


def load_coinmarketcap(data_path="./data"):
    hdf_store = pd.HDFStore(path=os.path.join(data_path, "data.hdf5"))
    data_dict = {d[2:]: convert_data(hdf_store[d]) for d in hdf_store.keys() if not hdf_store[d].empty}
    data = {}

    for x in data_dict[hdf_store.keys()[0][2:]].columns[2:]:
        data[x] = pd.DataFrame()
        for k in data_dict.keys():
            try:
                data[x][k] = data_dict[k][x]
            except KeyError:
                data[x][k] = np.nan
        try:
            data[x] = data[x].astype(float)
        except ValueError:
            pass
    
    hdf_store.close()

    return data

if __name__ == "__main__":
    cmc = CoinMarketCap(CMC_API_KEY)
    cmc.get_ohlcv_realtime(["BTC", "ETH", "ADA"])
    