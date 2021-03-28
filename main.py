from datetime import datetime, timedelta
import pytz as tz
import time
from Data.current_data_sequence import CurrentDataSequence
from Oanda.Services.order_handler import OrderHandler
from Oanda.Services.data_downloader import DataDownloader
from Model.stochastic_crossover import StochasticCrossover
from Model.macd_crossover import MacdCrossover
# from Model.beep_boop import BeepBoop
# from Model.cnn import ForexCNN
import traceback
import numpy as np

weekend_day_nums = [4, 5, 6]

stoch_macd_gain_risk_ratio = {'GBP_USD': 1.5, 'EUR_USD': 1.7}
stoch_macd_possible_pullback_cushions = {'GBP_USD': np.arange(34, 37), 'EUR_USD': np.arange(29, 32)}
stoch_macd_pullback_cushion = {'GBP_USD': 0.0035, 'EUR_USD': 0.0030}
stoch_macd_n_units_per_trade = {'GBP_USD': 50000, 'EUR_USD': 50000}
stoch_macd_rounding = {'GBP_USD': 5, 'EUR_USD': 5}
stoch_macd_max_pips_to_risk = {'GBP_USD': 0.0100, 'EUR_USD': 0.0100}
stoch_macd_use_trailing_stop = {'GBP_USD': False, 'EUR_USD': False}
stoch_macd_all_buys = {'GBP_USD': True, 'EUR_USD': True}
stoch_macd_all_sells = {'GBP_USD': True, 'EUR_USD': True}
stoch_macd_max_open_trades = {'GBP_USD': 1, 'EUR_USD': 1}
open_stoch_macd_pairs = {'GBP_USD': 0, 'EUR_USD': 0}
stoch_signals = {'GBP_USD': None, 'EUR_USD': None}
stoch_possible_time_frames = {'GBP_USD': np.arange(10, 12), 'EUR_USD': np.arange(6, 8)}
stoch_time_frames = {'GBP_USD': 10, 'EUR_USD': 6}
# stoch_counters = {'GBP_USD': 0, 'EUR_USD': 0, 'NZD_USD': 0}

# beep_boop_gain_risk_ratio = {'GBP_USD': 1.8}
# beep_boop_pullback_cushion = {'GBP_USD': 0.0050}
# beep_boop_n_units_per_trade = {'GBP_USD': 10000}
# beep_boop_rounding = {'GBP_USD': 5}
# beep_boop_max_pips_to_risk = {'GBP_USD': 0.0100}
# beep_boop_use_trailing_stop = {'GBP_USD': False}
# beep_boop_all_buys = {'GBP_USD': True}
# beep_boop_all_sells = {'GBP_USD': True}
# beep_boop_max_open_trades = {'GBP_USD': 5}
# open_beep_boop_pairs = {'GBP_USD': 0}

# beep_boop_gain_risk_ratio = {'GBP_USD': 1.3}
# beep_boop_pullback_cushion = {'GBP_USD': 0.0075}
# beep_boop_n_units_per_trade = {'GBP_USD': 10000}
# beep_boop_rounding = {'GBP_USD': 5}
# beep_boop_max_pips_to_risk = {'GBP_USD': 0.0100}
# beep_boop_use_trailing_stop = {'GBP_USD': True}
# open_beep_boop_pairs = {'GBP_USD': True}
#
# cnn_gain_risk_ratio = {'GBP_JPY': 1.7}
# cnn_pullback_cushion = {'GBP_JPY': 0.05}
# cnn_n_units_per_trade = {'GBP_JPY': 10000}
# cnn_rounding = {'GBP_JPY': 3}
# cnn_max_pips_to_risk = {'GBP_JPY': 1}
# cnn_use_trailing_stop = {'GBP_JPY': False}
# open_cnn_pairs = {'GBP_JPY': True}
# forex_cnn = ForexCNN()

current_data_sequence = CurrentDataSequence()
data_downloader = DataDownloader()


def _get_dt():
    utc_now = datetime.utcnow().replace(microsecond=0, second=0)

    if utc_now.weekday() in weekend_day_nums:
        if (utc_now.weekday() == 4 and utc_now.hour >= 20) or (
                utc_now.weekday() == 6 and utc_now.hour <= 21) or utc_now.weekday() == 5:
            print('Weekend hours, need to wait until market opens again.')

            while True:
                new_utc_now = datetime.utcnow().replace(microsecond=0, second=0)

                if new_utc_now.weekday() == 6 and new_utc_now.hour > 21:
                    break

    current_minutes = (datetime.now(tz=tz.timezone('America/New_York')).replace(microsecond=0, second=0)).minute
    dt_m5 = datetime.strptime((datetime.now(tz=tz.timezone('America/New_York')).replace(microsecond=0, second=0, minute=current_minutes - current_minutes % 5) + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')

    return dt_m5


def _get_open_trades(dt):
    try:
        global open_stoch_macd_pairs
        global stoch_macd_all_buys
        global stoch_macd_all_sells
        global stoch_macd_n_units_per_trade

        for currency_pair in open_stoch_macd_pairs:
            open_stoch_macd_pairs[currency_pair] = 0
            stoch_macd_n_units_per_trade[currency_pair] = 50000
            stoch_macd_all_buys[currency_pair] = True
            stoch_macd_all_sells[currency_pair] = True

        open_trades, error_message = OrderHandler.get_open_trades()

        if error_message is not None:
            print(error_message)

            while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
                time.sleep(1)

            return False

        for trade in open_trades:
            if trade.instrument in open_stoch_macd_pairs:
                # Increment the number of open trades for the given pair
                open_stoch_macd_pairs[trade.instrument] += 1

                # Increment the number of units (so that the next trade has a unique number of units in order to satisfy the
                # FIFO requirement)
                if abs(trade.currentUnits) >= stoch_macd_n_units_per_trade[trade.instrument]:
                    stoch_macd_n_units_per_trade[trade.instrument] = abs(trade.currentUnits) + 1

                # Determine if all the trades for the pair are buys or sells
                if trade.currentUnits < 0 and stoch_macd_all_buys[trade.instrument]:
                    stoch_macd_all_buys[trade.instrument] = False

                if trade.currentUnits > 0 and stoch_macd_all_sells[trade.instrument]:
                    stoch_macd_all_sells[trade.instrument] = False

        return True

    except Exception as e:
        error_message = 'Error when trying to get open trades'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return False


def _update_beep_boop_current_data_sequence(dt, currency_pair):
    try:
        current_data_update_success = current_data_sequence.update_beep_boop_current_data_sequence(currency_pair)

        if not current_data_update_success:
            print('Error updating beep boop data for ' + str(currency_pair))

            while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
                time.sleep(1)

            return False

        return True

    except Exception as e:
        error_message = 'Error when trying to get update ' + str(currency_pair) + ' beep boop current data sequence'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return False


def _update_cnn_current_data_sequence(dt, currency_pair):
    try:
        current_data_update_success = current_data_sequence.update_cnn_current_data_sequence(currency_pair)

        if not current_data_update_success:
            print('Error updating cnn data for ' + str(currency_pair))

            while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
                time.sleep(1)

            return False

        return True

    except Exception as e:
        error_message = 'Error when trying to get update ' + str(currency_pair) + ' cnn current data sequence'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return False


def _update_stoch_macd_current_data_sequence(dt, currency_pair):
    try:
        current_data_update_success = current_data_sequence.update_stoch_macd_current_data_sequence(currency_pair)

        if not current_data_update_success:
            print('Error updating stoch macd data for ' + str(currency_pair))

            while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
                time.sleep(1)

            return False

        return True

    except Exception as e:
        error_message = 'Error when trying to get update ' + str(currency_pair) + ' stoch macd current data sequence'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return False


def _get_current_data(dt, currency_pair, candle_types, time_granularity):
    try:
        candles, error_message = data_downloader.get_current_data(currency_pair, candle_types, time_granularity)

        if error_message is not None:
            print(error_message)

            while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
                time.sleep(1)

            return None

        return candles

    except Exception as e:
        error_message = 'Error when trying to get retrieve current market data'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return None


def _place_market_order(dt, currency_pair, pred, n_units_per_trade, profit_price, stop_loss, pips_to_risk, use_trailing_stop):
    try:
        OrderHandler.place_market_order(currency_pair, pred, n_units_per_trade, profit_price, stop_loss, pips_to_risk, use_trailing_stop)

        return True

    except Exception as e:
        error_message = 'Error when trying to place order'

        print(error_message)
        print(e)
        print(traceback.print_exc())

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt:
            time.sleep(1)

        return False


def _calculate_pips_to_risk(current_data, trade_type, pullback_cushion, bid_open, ask_open):
    pullback = None
    i = current_data.shape[0] - 4

    if trade_type == 'buy':
        while i >= 0:
            curr_fractal = current_data.loc[current_data.index[i], 'fractal']

            if curr_fractal == 1:
                pullback = current_data.loc[current_data.index[i], 'Bid_Low']
                break

            i -= 1

    elif trade_type == 'sell':
        while i >= 0:
            curr_fractal = current_data.loc[current_data.index[i], 'fractal']

            if curr_fractal == 2:
                pullback = current_data.loc[current_data.index[i], 'Ask_High']
                break

            i -= 1

    if pullback is not None and trade_type == 'buy':
        stop_loss = pullback - pullback_cushion

        if stop_loss >= ask_open:
            return None, None

        pips_to_risk = ask_open - stop_loss

        return pips_to_risk, stop_loss

    elif pullback is not None and trade_type == 'sell':
        stop_loss = pullback + pullback_cushion

        if stop_loss <= bid_open:
            return None, None

        pips_to_risk = stop_loss - bid_open

        return pips_to_risk, stop_loss

    else:
        return None, None


def main():
    global stoch_signals
    # global stoch_counters
    global stoch_time_frames
    global stoch_macd_pullback_cushion

    dt_m5 = _get_dt()

    open_trades_success = _get_open_trades(dt_m5)

    if not open_trades_success:
        main()

    for currency_pair in open_stoch_macd_pairs:
        print('Starting new session with stoch macd open for ' + str(currency_pair) + ': ' + str(open_stoch_macd_pairs[currency_pair]))

    while True:
        dt_m5 = _get_dt()

        error_flag = False

        print('\n---------------------------------------------------------------------------------')
        print('---------------------------------------------------------------------------------')
        print('---------------------------------------------------------------------------------')
        print(dt_m5)
        print()

        open_trades_success = _get_open_trades(dt_m5)

        if not open_trades_success:
            continue

        # --------------------------------------------------------------------------------------------------------------
        # ------------------------------------------------ STOCH MACD --------------------------------------------------
        # --------------------------------------------------------------------------------------------------------------

        data_sequences = {}

        for currency_pair in open_stoch_macd_pairs:
            current_data_update_success = _update_stoch_macd_current_data_sequence(dt_m5, currency_pair)

            if not current_data_update_success:
                error_flag = True
                break

            data_sequences[currency_pair] = current_data_sequence.get_stoch_macd_sequence_for_pair(currency_pair)
            print()
            print(data_sequences[currency_pair])
            print()

        if error_flag:
            continue

        for currency_pair in stoch_signals:
            # if stoch_counters[currency_pair] >= stoch_time_frames[currency_pair]:
            #     stoch_signals[currency_pair] = None
            #     stoch_counters[currency_pair] = 0
            #     stoch_time_frames[currency_pair] = np.random.choice(stoch_possible_time_frames[currency_pair], p=[0.70, 0.30])

            new_stoch_signal = StochasticCrossover.predict(currency_pair, data_sequences[currency_pair], stoch_time_frames[currency_pair])

            # if new_stoch_signal is not None:
            #     stoch_signals[currency_pair] = new_stoch_signal
            #     # stoch_counters[currency_pair] = 0
            #     stoch_time_frames[currency_pair] = np.random.choice(stoch_possible_time_frames[currency_pair], p=[0.70, 0.30])

            stoch_signals[currency_pair] = new_stoch_signal
            stoch_time_frames[currency_pair] = np.random.choice(stoch_possible_time_frames[currency_pair], p=[0.70, 0.30])

        predictions = {}

        for currency_pair in data_sequences:
            if open_stoch_macd_pairs[currency_pair] < stoch_macd_max_open_trades[currency_pair]:
                pred = MacdCrossover.predict(currency_pair, data_sequences[currency_pair], stoch_signals[currency_pair])
                predictions[currency_pair] = pred

        for currency_pair in stoch_time_frames:
        # for currency_pair in stoch_counters:
            # stoch_counters[currency_pair] += 1

            print('Stoch signal for ' + str(currency_pair) + ': ' + str(stoch_signals[currency_pair]))
            print('Stoch time frame ' + str(currency_pair) + ': ' + str(stoch_time_frames[currency_pair]))
            # print('Stoch counter for ' + str(currency_pair) + ': ' + str(stoch_counters[currency_pair]))
            print('-------------------------------------------------------\n')

        for currency_pair in predictions:
            pred = predictions[currency_pair]

            if pred is not None and ((pred == 'buy' and stoch_macd_all_buys[currency_pair]) or (pred == 'sell' and stoch_macd_all_sells[currency_pair])):
                stoch_macd_pullback_cushion[currency_pair] = np.random.choice(stoch_macd_possible_pullback_cushions[currency_pair], p=[0.20, 0.60, 0.20]) / 10000
                print('Stoch pullback cushion for ' + str(currency_pair) + ': ' + str(stoch_macd_pullback_cushion[currency_pair]))

                most_recent_data = False

                while not most_recent_data:
                    most_recent_data = True
                    candles = _get_current_data(dt_m5, currency_pair, ['bid', 'ask'], 'M5')

                    if candles is None:
                        error_flag = True
                        break

                    if candles[-1].complete:
                        print('The current market data is not available yet: ' + str(candles[-1].time))
                        most_recent_data = False

                if error_flag:
                    break

                last_candle = candles[-1]
                curr_bid_open = float(last_candle.bid.o)
                curr_ask_open = float(last_candle.ask.o)
                gain_risk_ratio = stoch_macd_gain_risk_ratio[currency_pair]
                pips_to_risk, stop_loss = _calculate_pips_to_risk(data_sequences[currency_pair], pred, stoch_macd_pullback_cushion[currency_pair], curr_bid_open, curr_ask_open)

                if pips_to_risk is not None and pips_to_risk <= stoch_macd_max_pips_to_risk[currency_pair]:
                    stoch_signals[currency_pair] = None

                    print('----------------------------------')
                    print('-- PLACING NEW ORDER (STOCH MACD) --')
                    print('------------ ' + str(currency_pair) + ' -------------')
                    print('----------------------------------\n')

                    n_units_per_trade = stoch_macd_n_units_per_trade[currency_pair]

                    if pred == 'buy':
                        profit_price = round(curr_ask_open + (gain_risk_ratio * pips_to_risk), stoch_macd_rounding[currency_pair])

                    else:
                        profit_price = round(curr_bid_open - (gain_risk_ratio * pips_to_risk), stoch_macd_rounding[currency_pair])

                    print('Action: ' + str(pred) + ' for ' + str(currency_pair))
                    print('Profit price: ' + str(profit_price))
                    print('Stop loss price: ' + str(stop_loss))
                    print('Pips to risk: ' + str(pips_to_risk))
                    print('Rounded pips to risk: ' + str(round(pips_to_risk, stoch_macd_rounding[currency_pair])))
                    print()

                    order_placed = _place_market_order(dt_m5, currency_pair, pred, n_units_per_trade, profit_price,
                                                       round(stop_loss, stoch_macd_rounding[currency_pair]),
                                                       round(pips_to_risk, stoch_macd_rounding[currency_pair]),
                                                       stoch_macd_use_trailing_stop[currency_pair])

                    if not order_placed:
                        error_flag = True
                        break

                else:
                    print('Pips to risk is none or too high: ' + str(pips_to_risk))

        if error_flag:
            continue

        # --------------------------------------------------------------------------------------------------------------
        # --------------------------------------------------------------------------------------------------------------
        # --------------------------------------------------------------------------------------------------------------

        # # --------------------------------------------------------------------------------------------------------------
        # # ------------------------------------------------- BEEP BOOP --------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------
        #
        # data_sequences = {}
        #
        # for currency_pair in open_stoch_macd_pairs:
        #     if open_stoch_macd_pairs[currency_pair] < stoch_macd_max_open_trades[currency_pair]:
        #         current_data_update_success = _update_beep_boop_current_data_sequence(dt_m5, currency_pair)
        #
        #         if not current_data_update_success:
        #             error_flag = True
        #             break
        #
        #         data_sequences[currency_pair] = current_data_sequence.get_beep_boop_sequence_for_pair(currency_pair)
        #
        # if error_flag:
        #     continue
        #
        # predictions = {}
        #
        # for currency_pair in data_sequences:
        #     pred = BeepBoop.predict(currency_pair, data_sequences[currency_pair])
        #     predictions[currency_pair] = pred
        #
        # for currency_pair in predictions:
        #     pred = predictions[currency_pair]
        #
        #     if pred is not None and ((pred == 'buy' and stoch_macd_all_buys[currency_pair]) or (pred == 'sell' and stoch_macd_all_sells[currency_pair])):
        #         most_recent_data = False
        #
        #         while not most_recent_data:
        #             most_recent_data = True
        #             candles = _get_current_data(dt_m5, currency_pair, ['bid', 'ask'], 'H1')
        #
        #             if candles is None:
        #                 error_flag = True
        #                 break
        #
        #             if candles[-1].complete:
        #                 print('The current market data is not available yet: ' + str(candles[-1].time))
        #                 most_recent_data = False
        #
        #         if error_flag:
        #             break
        #
        #         last_candle = candles[-1]
        #         curr_bid_open = float(last_candle.bid.o)
        #         curr_ask_open = float(last_candle.ask.o)
        #         gain_risk_ratio = stoch_macd_gain_risk_ratio[currency_pair]
        #         pips_to_risk, stop_loss = _calculate_pips_to_risk(data_sequences[currency_pair], pred, stoch_macd_pullback_cushion[currency_pair], curr_bid_open, curr_ask_open)
        #
        #         if pips_to_risk is not None and pips_to_risk <= stoch_macd_max_pips_to_risk[currency_pair]:
        #             print('----------------------------------')
        #             print('-- PLACING NEW ORDER (BEEP BOOP) --')
        #             print('------------ ' + str(currency_pair) + ' -------------')
        #             print('----------------------------------\n')
        #
        #             n_units_per_trade = stoch_macd_n_units_per_trade[currency_pair]
        #
        #             if pred == 'buy':
        #                 profit_price = round(curr_ask_open + (gain_risk_ratio * pips_to_risk), stoch_macd_rounding[currency_pair])
        #
        #             else:
        #                 profit_price = round(curr_bid_open - (gain_risk_ratio * pips_to_risk), stoch_macd_rounding[currency_pair])
        #
        #             print('Action: ' + str(pred) + ' for ' + str(currency_pair))
        #             print('Profit price: ' + str(profit_price))
        #             print('Stop loss price: ' + str(stop_loss))
        #             print('Pips to risk: ' + str(pips_to_risk))
        #             print('Rounded pips to risk: ' + str(round(pips_to_risk, stoch_macd_rounding[currency_pair])))
        #             print()
        #
        #             order_placed = _place_market_order(dt_m5, currency_pair, pred, n_units_per_trade, profit_price,
        #                                                round(stop_loss, stoch_macd_rounding[currency_pair]),
        #                                                round(pips_to_risk, stoch_macd_rounding[currency_pair]),
        #                                                stoch_macd_use_trailing_stop[currency_pair])
        #
        #             if not order_placed:
        #                 error_flag = True
        #                 break
        #
        #         else:
        #             print('Pips to risk is none or too high: ' + str(pips_to_risk))
        #
        # if error_flag:
        #     continue
        #
        # # --------------------------------------------------------------------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------

        # # --------------------------------------------------------------------------------------------------------------
        # # --------------------------------------------------- CNN -----------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------
        #
        # gasf_data_vals = {}
        # price_data_vals = {}
        #
        # for currency_pair in open_cnn_pairs:
        #     if not open_cnn_pairs[currency_pair]:
        #         current_data_update_success = _update_cnn_current_data_sequence(dt_m5, currency_pair)
        #
        #         if not current_data_update_success:
        #             error_flag = True
        #             break
        #
        #         gasf_data, price_data = current_data_sequence.get_cnn_sequence_for_pair(currency_pair)
        #
        #         gasf_data_vals[currency_pair] = gasf_data
        #         price_data_vals[currency_pair] = price_data
        #
        # if error_flag:
        #     continue
        #
        # predictions = {}
        #
        # for currency_pair in gasf_data_vals:
        #     pred = forex_cnn.predict(currency_pair, gasf_data_vals[currency_pair])
        #     predictions[currency_pair] = pred
        #
        # for currency_pair in predictions:
        #     pred = predictions[currency_pair]
        #
        #     if pred is not None:
        #         most_recent_data = False
        #
        #         while not most_recent_data:
        #             most_recent_data = True
        #             candles = _get_current_data(dt_m5, currency_pair, ['bid', 'ask'], 'H1')
        #
        #             if candles is None:
        #                 error_flag = True
        #                 break
        #
        #             if candles[-1].complete:
        #                 print('The current market data is not available yet: ' + str(candles[-1].time))
        #                 most_recent_data = False
        #
        #         if error_flag:
        #             break
        #
        #         last_candle = candles[-1]
        #         curr_bid_open = float(last_candle.bid.o)
        #         curr_ask_open = float(last_candle.ask.o)
        #         gain_risk_ratio = cnn_gain_risk_ratio[currency_pair]
        #         pips_to_risk, stop_loss = _calculate_pips_to_risk(price_data_vals[currency_pair], pred, cnn_pullback_cushion[currency_pair], curr_bid_open, curr_ask_open)
        #
        #         if pips_to_risk is not None and pips_to_risk <= cnn_max_pips_to_risk[currency_pair]:
        #             print('----------------------------------')
        #             print('-- PLACING NEW ORDER (CNN) --')
        #             print('------------ ' + str(currency_pair) + ' -------------')
        #             print('----------------------------------\n')
        #
        #             n_units_per_trade = cnn_n_units_per_trade[currency_pair]
        #
        #             if pred == 'buy':
        #                 profit_price = round(curr_ask_open + (gain_risk_ratio * pips_to_risk), cnn_rounding[currency_pair])
        #
        #             else:
        #                 profit_price = round(curr_bid_open - (gain_risk_ratio * pips_to_risk), cnn_rounding[currency_pair])
        #
        #             print('Action: ' + str(pred) + ' for ' + str(currency_pair))
        #             print('Profit price: ' + str(profit_price))
        #             print('Stop loss price: ' + str(stop_loss))
        #             print('Pips to risk: ' + str(pips_to_risk))
        #             print('Rounded pips to risk: ' + str(round(pips_to_risk, cnn_rounding[currency_pair])))
        #             print()
        #
        #             order_placed = _place_market_order(dt_m5, currency_pair, pred, n_units_per_trade, profit_price,
        #                                                round(stop_loss, cnn_rounding[currency_pair]),
        #                                                round(pips_to_risk, cnn_rounding[currency_pair]),
        #                                                cnn_use_trailing_stop[currency_pair])
        #
        #             if not order_placed:
        #                 error_flag = True
        #                 break
        #
        #         else:
        #             print('Pips to risk is none or too high: ' + str(pips_to_risk))
        #
        # if error_flag:
        #     continue
        #
        # # --------------------------------------------------------------------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------
        # # --------------------------------------------------------------------------------------------------------------

        # Give Oanda a few seconds to process the trades
        time.sleep(15)

        open_trades_success = _get_open_trades(dt_m5)

        if not open_trades_success:
            continue

        for currency_pair in open_stoch_macd_pairs:
            print('Open stoch macd trade for ' + str(currency_pair) + ': ' + str(open_stoch_macd_pairs[currency_pair]) + '\n')

        # for currency_pair in open_cnn_pairs:
        #     print('Open cnn trade for ' + str(currency_pair) + ': ' + str(open_cnn_pairs[currency_pair]) + '\n')

        for currency_pair in stoch_macd_all_buys:
            print('All buys for ' + str(currency_pair) + ': ' + str(stoch_macd_all_buys[currency_pair]))

        for currency_pair in stoch_macd_all_sells:
            print('All sells for ' + str(currency_pair) + ': ' + str(stoch_macd_all_sells[currency_pair]))

        while datetime.strptime((datetime.now(tz=tz.timezone('America/New_York'))).strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S') < dt_m5:
            time.sleep(1)

        print('---------------------------------------------------------------------------------')
        print('---------------------------------------------------------------------------------')
        print('---------------------------------------------------------------------------------')


if __name__ == "__main__":
    main()
