from binance_api2 import BApi
from candles_counter import candles_counter
import pandas as pd 
import datetime 
import logging
logging.basicConfig(level=logging.INFO,filename='bot.log',filemode='w')
import time 
import winsound

class candlebot:
    def __init__(self,binance_config='./configs/binance_api.json') -> None:
        self.b=BApi(api_config=binance_config)          # binance api object 
        self.df=None                                    # dataframe with data 
        self.last_n_cnt= 5                              # buy after n consecutive red candles ! 
        self.end_of_candle_cutoff=30                    # buy in last 10 seconds of interval 
        self.loop_frequency=20                          # should be lower than end of candle cutoff
        self.time_format='%Y-%m-%d %H:%M:%S'
        self.dt_fun = lambda t1,t2: int((datetime.datetime.strptime(t1,self.time_format)-datetime.datetime.strptime(t2,self.time_format)).total_seconds())

        self.trades_d={                                 # dictionary with api response 
                     'symbol': None               # 'ADABUSD', 
                     ,'orderId': None             #  int(datetime.datetime.now().timestamp()),
                     ,'orderListId':None          # -1,
                     ,'clientOrderId':None        # 'N0OWokxZgkcR9jwf1WdIJP',
                     ,'transactTime':None         #  1668283104455,
                     ,'price':None                #  str(price),
                     ,'origQty': None             #  '57.60000000',
                     ,'executedQty': None         #  '57.60000000', 
                     ,'cummulativeQuoteQty': None #  '19.79712000',
                     ,'status': None              # 'FILLED',
                     ,'timeInForce': None         #  'GTC',
                     ,'type': None                # 'MARKET',
                     ,'side': None                # 'SELL', 
                     ,'fills': None               #  [{'price': '0.34370000', 'qty': '57.60000000', 
                     }                            #'commission': '0.01979712', #'commissionAsset': 'BUSD', 'tradeId': 92820107}]}
        self.trades_df=pd.DataFrame(self.trades_d,index=[0])
        # dictionary with assertions 
        self.assertion_d={                                
            'end_of_candle':self.assertion_end_of_candle
            ,'currently_red':self.assertion_currently_red
            ,'last_n_red':self.assertion_last_n_red   
        }
        self.check_assertions = lambda : all([v() for k,v in self.assertion_d.items()]) # function to check if all assertions are ok  
            
        # pnl structures for stop losses and take profits 
        self.pnl_sl=0.99        # stop loss 
        self.pnl_tp=1.01        # take profit 
        self.tr_sl=0.99         # trailing stop loss 
        self.pnl_d={'tradeid':None,
                    'price':None,
                    'status':None,
                    'cur_pnl':None,
                    'max_pnl':None or -1,
                    'min_pnl':None or 999 ,
                    'symbol': None, # symbol used to update pnl data 
                    'sl_price':None,'tp_price':None,'trailing_tp_price':None,'comment':None}
        # pnl statuses:
            # FILLED -> filled market sell order 
            # OPEN-LONG -> filled market buy order 
            # CLOSED-LONG -> closed market buy 
        self.pnl_df=pd.DataFrame(self.pnl_d,index=[0])
        self.trading_symbol='ADAUSDT' # let's do only one symbol now 
        # structure for actions 
        self.actions_d={
            'market_buy':self.market_buy
            ,'market_sell':self.market_sell_tradeid
            ,'update_pnl_df':self.update_pnl_df # to do 
            ,'execute_sl':self.execute_sl       # to do 
            ,'execute_tp':self.execute_tp       # to do 
            ,'execute_trtp':self.execute_trtp   # to do 
        }
    
    
    def log_variable(self,var,msg='',wait=False):
        if var is None:
            var='None'
        s= f' {msg} : {var}'
        logging.info(s)
        if wait:
            print(s)
            input('waiting in log ')
    # puts nones to a traded d 
    def clear_d(self,d=None):
        if d is None: 
            d=self.trades_d
        d={k:None for k in d.keys()}
        
    # inserts d to a trade_df
    def save_to_df(self,d=None,df=None):
        if d is None: # defaults
            d=self.trades_d
        if df is None: # defaults to trades df 
            df=self.trades_df
        df.loc[len(df)]=d
    
    # gets df from api 
    def get_df_from_api(self,scale='1min',interval='1hour'):
        klines=self.b.get_recent_candles(symbol=self.trading_symbol,scale=scale,interval=interval)
        self.df=self.b.parsed_kline_list_to_df(parsed_kline_list=klines)
        if 0:
            print('zump it')
            self.df.to_csv('./data/test_df.csv',index=False)
        
        
    # adds green_cnt and red_cnt to a df 
    def calculate_counts(self):
        self.df['green']=self.df['open']<self.df['close']
        self.df['red'] = self.df['open']>=self.df['close']
        self.df['green']=self.df['green'].astype(int)
        self.df['red']=self.df['red'].astype(int)
        self.df['green_cnt']=candles_counter(self.df['green'])*self.df['green']
        self.df['red_cnt']=candles_counter(self.df['red'])*self.df['red'] # gotta multiply dont worry fren 
        if 1: # ze drop 
            self.df.drop(columns=['green','red'],inplace=True ) 
        
    # returns True if we are near the end of the candle 
    def assertion_end_of_candle(self):
        if self.df is None:
            return False
        dt1=self.b.get_server_time()            # server time 
        dt2=self.df.iloc[-1]['close_utc']       # current candle utc close time 
        dt=self.dt_fun(dt2,dt1)                 # seconds between
        return dt<=self.end_of_candle_cutoff    # are we at the end of the candle? 
    
    # returns True if current candle is red  - duplicate counters job though 
    def assertion_currently_red(self,scale='1min',interval='15min'):
        self.get_df_from_api(scale=scale,interval=interval)             # refresh dataframe 
        last_row=self.df.iloc[-1]                                       # get last row because it's nice to have a variable for everything 
        return last_row['open']>=last_row['close']                      # return True if red 
 
    # returns True if last n candles were red 
    def assertion_last_n_red(self,colname='red_cnt',n=-1):
        if colname not in self.df.columns:  # if there is no colname in df execute counter to get it 
            self.calculate_counts()
        last_row=self.df.iloc[-1]
        if n ==-1: # if n not provided use instance attribute 
            n=self.last_n_cnt
        return last_row[colname]>=n
    
    # market buys by orderid 
    def market_buy(self,dollar_amo=20,pnl_comment='',test_order=False):
        response,status=self.b.market_buy_dollar_amo(symbol=self.trading_symbol,dollar_amo=dollar_amo)
        self.trades_d=response
        self.save_to_df()
        self.clear_d()
        
        # update pnl data  if order got filled 
        print('check order statuses for partial filled here ')
        if status =='FILLED':
            self.pnl_d['symbol']=response['symbol']
            self.pnl_d['tradeid']=response['orderId']
            self.pnl_d['price']=response['price']
            self.pnl_d['status']='OPEN-LONG'
            self.pnl_d['comment']=pnl_comment
            self.save_to_df(d=self.pnl_d,df=self.pnl_df)
            self.clear_d(d=self.pnl_d)
        return response 
            
    # market sells by order id and updates pnl df 
    def market_sell_tradeid(self,orderid,pnl_comment='',test_order=False):
        response,status = self.b.market_sell_orderid(orderid=orderid,symbol=self.trading_symbol)      
        self.trades_d=response 
        self.save_to_df()
        self.clear_d()
        
        if status =='FILLED':
            self.pnl_d['symbol']=response['symbol']
            self.pnl_d['tradeid']=response['orderId']
            self.pnl_d['price']=response['price']
            self.pnl_d['status']='FILLED'
            self.pnl_d['comment']=pnl_comment
            self.save_to_df(d=self.pnl_d,df=self.pnl_df)
            self.clear_d(d=self.pnl_d)
            
            msk=self.pnl_df['tradeid']==orderid # close long in pnl_df
            index=self.pnl_df[msk].index.values
            self.pnl_df.loc[index,'status']='CLOSED-LONG'
        return response
        
    # updates pnls df with each price 
    def update_pnl_df(self):
        response=self.b.check_current_price(symbol=self.trading_symbol)  # check price for a row this shouldn't be done in a loop but whatever.
        key='close' # current price assumption 
        for index,row in self.pnl_df.iterrows():
            if row['tradeid'] is None: # first row is full of nones
                continue
            if row['status'] !='OPEN-LONG':
                continue
                
            current_price=response[key]
            cur_pnl=current_price/float(row['price']) # one endpoint returns stuff as float another as str meh 
            self.pnl_df.loc[index,'cur_pnl']=cur_pnl
            if cur_pnl>row['max_pnl']:
                self.pnl_df.loc[index,'max_pnl']=cur_pnl=cur_pnl
            if cur_pnl<row['min_pnl']:
               self.pnl_df.loc[index,'min_pnl']=cur_pnl=cur_pnl
        
    # iterates over pnl df and closes rows which have pnl < cutoff 
    def execute_sl(self,force=False, pnl_comment =''):
        for index,row in self.pnl_df.iterrows():
            if index==0: # skipping first row 
                continue
            if row['status']!='OPEN-LONG': # skipping pnl rows that are not open-long status 
                continue
            pnl=row['cur_pnl']
            if pnl<self.pnl_sl or force:
                self.market_sell_tradeid(orderid=row['tradeid'],pnl_comment=f'SL  {pnl_comment}')

    # iterates over pnl df and closes rows which have pnl > cutoff 
    def execute_tp(self,force=False,pnl_comment=''):
        for index,row in self.pnl_df.iterrows():
            if index==0: # skipping first row 
                continue
            if row['status']!='OPEN-LONG':
                continue
            
            pnl=row['cur_pnl']
            if pnl>self.pnl_tp or force:
                self.market_sell_tradeid(orderid=row['tradeid'],pnl_comment=f'TP {pnl_comment}')

    # iterates over pnl df and closes rows which have cur_pnl/max_pnl < pnl_cutoff
    def execute_trtp(self,force=False, pnl_comment=''):
        for index,row in self.pnl_df.iterrows():
            if index==0:
                continue
            if row['status']!='OPEN-LONG':
                continue
            tr_pnl=row['cur_pnl']/row['max_pnl']
            if tr_pnl<self.tr_sl or force:
                self.market_sell_tradeid(orderid=row['tradeid'],pnl_comment=f'TRTP {pnl_comment}')
    
    
    # simple strategy for buying on n red candles, selling when SL or TRTP or TP , or when n green candles happen 
    def simple_strategy(self,symbol=None,n_candles=2):
        if symbol is None: 
            self.trading_symbol='ADAUSDT'
            
        self.get_df_from_api(scale='1min',interval='15min') # get df 
        self.calculate_counts()
        print(self.df.to_string())
        print(datetime.datetime.now())
        print('-----')
        self.last_n_cnt=n_candles         # buy after n candles red 
        self.end_of_candle_cutoff=15      # buy in last n seconds of a candle 
        assertions_met=self.check_assertions()
        
        if assertions_met:
            winsound.Beep(500,1000)
            print('making a trade!')
            self.log_variable(var='', msg = ' buying bags ')
            
            self.update_pnl_df()
            r=self.market_buy(dollar_amo=20, pnl_comment=' buy after assertion  ')
            self.update_pnl_df()
        
        green_candles_assertion=self.assertion_last_n_red(colname='green_cnt',n=2)
        if green_candles_assertion:
            print('selling bags ')
            self.log_variable(var='', msg = ' selling bags ')
            winsound.Beep(500,2000)
            var=self.b.get_historical_orders(symbol=self.trading_symbol,last_n=2)
#            self.execute_sl(force=True,pnl_comment='selling on green candles ! ')
            self.b.try_to_close_all_by_symbol(symbol=self.trading_symbol)       

        self.execute_tp(pnl_comment='executing tp ')
        self.execute_sl(pnl_comment='executing sl ')
#        self.execute_trtp()





if __name__=='__main__':
    c=candlebot()
    while True:
        c.simple_strategy()
        time.sleep(15)

    exit(1)



    
    
   

                     