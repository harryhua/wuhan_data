import sys
from sklearn import preprocessing # add by sandy
from sklearn import svm
from sklearn.svm import LinearSVC
from utils import *
# import configuration file and figure out what to run
from config import *
import random
import datetime

models = dict()

def test_only_0a(df,par):
# testing multiple datasets I/O and .csv I/O
    print(df[0])
    print(df[1])
    return df

def read_train_data_1a(df, par):
    return readZipCSV(par['dir'], par['fname'])

def read_test_data_1b(df, par):
    return readZipCSV(par['dir'], par['fname'])

def summarize_data_2a(df, par):
    colNames = list(df.columns.values)
    print("==================================================== Summary ===================================================")
    print("nrows: ",df.shape[0],"ncols: ",df.shape[1])
    print(df.describe())
    print("%20s %15s %15s" % ("column","num_missing","missing_rate"))
    for c in colNames:
        nMiss = df[c].isnull().sum()
        print("%20s %15d %15.4f" % (c,nMiss,nMiss/df.shape[0]))
    print("================================================================================================================")
    return None

def filter_records_2a(df, par):
    return filterUnmatchedRecord(df)

def recode_features_2b(df, par):
    """
    Recode some continuous original features and append to the same data set
    df[0] is the dataset to be recoded (train/test).
    df[1] is the dataset that provides help (train).
    notice that this function is project specific -- Allstate only
    """
    recoded_features = df[0]
    helper_features = df[1]

    car_value_map = {'a':0,'b':1,'c':2,'d':3,'e':4,'f':5,'g':6,'h':7,'i':8}
    recoded_features['car_value'] = recoded_features['car_value'].apply(lambda x: car_value_map.get(x))
    recoded_features['hour'] = recoded_features['time'].apply(lambda x: int(x.split(':')[0]))
    recoded_features['r_hour'] = pd.cut(recoded_features['hour'],[-1,6,12,18,24]).labels
    recoded_features['r_car_age'] = pd.cut(recoded_features['car_age'],[-1,3,7,12,100]).labels
    recoded_features['r_age_oldest'] = pd.cut(recoded_features['age_oldest'],[-1,28,44,60,100]).labels
    recoded_features['r_age_youngest'] = pd.cut(recoded_features['age_youngest'],[-1,26,40,57,100]).labels
    recoded_features['r_cost'] = pd.cut(recoded_features['cost'],[-1,605,635,665,1000]).labels
    bought = helper_features.loc[helper_features['record_type']==1,:]
    bought_count = bought.groupby('location')['location'].count()
    rhash = bought_count.apply(lambda x: int(x>10)+int(x>15)+int(x>25))
    recoded_features['r_location'] = recoded_features['location'].apply(lambda row: rhash.get(row))

    return [recoded_features]


def analyze_2fy(df, par):
    """
    notice that this function is project specific -- Allstate only
    """
    if par.get('log') != None:
        log = open(par['log'], 'w')
    else:
        log = sys.stdout
    df['hour'] = df.loc[:,'time'].apply(lambda x: x.split(':')[0])

    for c in ['state','location','day','hour']:
        print1DRiskTable(gen1DRiskTable(df,c,'record_type',1),log)

    if par.get('log') != None:
        log.close()
    return None

def create_static_features_3a(df, par):
# TODO: This function fails when par['condprob'][0] or par['condprob'][1] has only one variable in the list
    """
    Create static features based on original/recoded features and return a new data set
    df[0] is the dataset to create features on (train/test).
    df[1] is the dataset that provides help (train).
    notice that this function is project specific -- Allstate only
    """

    input_features = df[0]
    helper_features = df[1]

    firstVarList = par['condprob'][0]
    secondVarList = par['condprob'][1]

    if not firstVarList:
        print("ERROR: failed to create static features based on an empty list.")
        return None

    bought = helper_features.loc[helper_features['record_type']==1,:]
    static_features = {}

    if not secondVarList:
        for A in firstVarList:
            print("Generating cpt for {}".format(A))
            cpt = genCondProbTable(bought,[A],[])
            static_features['p_'+A] = genCondProbVar(input_features,cpt)
    else:
        for A in firstVarList:
            for B in secondVarList:
                print("Generating cpt for {} | {}".format(A,B))
                cpt = genCondProbTable(bought,[A],[B])
                static_features['p_'+A+'_'+B] = genCondProbVar(input_features,cpt)

    return [pd.DataFrame(static_features)]

#Sandy: create dynamic features
# question to yangfan: what is helper_features used to?
def create_dynamic_features_3b(df,par):
    input_features = df[0]
    #helper_features = df[1]
    duplicate_method = par['method_duplicate']
    merge_col_option = mergeOptionsCol(input_features)
    df_mergeOption = pd.concat([input_features,merge_col_option],axis=1)
    df_small = df_mergeOption.loc[:,['customer_ID','option_combine','record_type']]

    isDuplicate = []    # column "is_Duplicate"
    isLastQuote = []    # column "is_LastQuote"
    quote_frequency = []    # column "quote_Frequency"
    quote_percent = []  # column "quote_Percent"

    rowindex = len(df_small)
    i = 0   # index of the start row of one customer
    j = 0   # index of the start row of next customer
    while (j < rowindex):
        current_customerID = df_small.loc[i,'customer_ID']
        # move j to the start row of next customer
        while ((df_small.iloc[j,0] == current_customerID)):
            j +=1
            if j == rowindex:
                break

        k = j - 1   # set k to the end row of current customer
        quote_count = j - i # the total number of quotes for current customer
        if (quote_count < 1):
            print ("Error: number of quote history is less than 1")
        option_set = set()  # a set used to check the duplicate option_combine
        option_dict = {}    # a dictionary to record the frequency for each option_combine
        # last quote for current customer
        if (df_small.loc[k, 'record_type'] == 0):
            last_quote = df_small.loc[k,'option_combine']
        elif (quote_count > 1):
            last_quote = df_small.loc[k-1,'option_combine']
        else:
            last_quote = -1     # no last quote for this customer
        # iterate all rows for current customer from backward
        while (k>=i):
            option_value = df_small.loc[k,'option_combine']
            record_type = df_small.loc[k,'record_type']
            # compute the value for column of "is_Duplicate"
            if (option_value in option_set):
                isDuplicate.insert(i,1)
            else:
                isDuplicate.insert(i,0)
                if (duplicate_method == 1):     #only label the duplicate in row with record_type ==0
                    if (record_type == 0):
                        option_set.add(option_value)
                else:
                    option_set.add(option_value)
            # count the frequency for each option_combine
            if (option_value in option_dict):
                option_dict[option_value] += 1
            else:
                option_dict[option_value] = 1
            k -= 1
        # iterate all rows to set the value for column "is_LastQuote", "quote_Frequency" and "quote_Percent"
        t = i
        while (t < j):
            option = df_small.loc[t,'option_combine']
            frequency = option_dict[option]
            quote_frequency.append(frequency)
            #quote_percent.append(round(frequency*1.0/quote_count,2))
            quote_percent.append(frequency*1.0/quote_count)
            # compute the value for column of "is_LastQuote"
            if (option == last_quote):
                isLastQuote.append(1)
            else:
                isLastQuote.append(0)
            t +=1
        i = j

    isDuplicate_df = pd.DataFrame(isDuplicate,index = list(range(rowindex)),columns=['is_Duplicate'])
    isLastQuote_df = pd.DataFrame(isLastQuote,index = list(range(rowindex)),columns=['is_LastQuote'])
    quote_frequency_df = pd.DataFrame(quote_frequency,index = list(range(rowindex)),columns=['quote_Frequency'])
    quote_percent_df = pd.DataFrame(quote_percent,index = list(range(rowindex)),columns=['quote_Percent'])
    dynamic_features = pd.concat([isDuplicate_df,isLastQuote_df, quote_frequency_df, quote_percent_df], axis =1)
    return dynamic_features
   

def merge_datasets_3z(df, par):
    origin_train = df[0]
    static_dataset = df[1]
    dynamic_dataset = df[2]
    handle_duplicate = par['handle_duplicate']
    print(len(origin_train))
    train_select = origin_train.loc[:,['customer_ID','A','B','C','D','E','F','G','record_type']]
    train_pool_full = pd.concat([static_dataset,dynamic_dataset, train_select], axis = 1)
    dataset_update = train_pool_full    
    if (handle_duplicate == 1):
        dataset_update = filterDuplicate(train_pool_full)
    train_target = pd.DataFrame(dataset_update.loc[:,'record_type'], columns = ['record_type'])
    print(len(train_target))
    customer_ID = pd.DataFrame(dataset_update.loc[:,'customer_ID'], columns = ['customer_ID'])
    train_pool = dataset_update.drop(['record_type','customer_ID','is_Duplicate'],axis=1)
    return [train_pool, train_target, customer_ID]

#sandy: data preprocessing
def preprocess_train_4a(df, par):
    df_keep = df.loc[:,['A','B','C','D','E','F','G','is_LastQuote']]
    df_preprocess = df.drop(['A','B','C','D','E','F','G','is_LastQuote'], axis=1)
    dataset_nomissing = handleMissing (df_preprocess, par['missing'])
    dataset_norm = Normalize(dataset_nomissing)
    data_preprocess = pd.concat([df_keep,dataset_norm], axis = 1)
    return data_preprocess

#taku: feature selection
def feature_selection_4b(df, par):
    df_data = df[0]
    df_y = df[2]
    selected_features = df[1]
    df_options = df_data.loc[:,['A', 'B', 'C', 'D', 'E', 'F', 'G']]
    df_without_options = df_data.drop(['A', 'B', 'C', 'D', 'E', 'F', 'G'], axis = 1) #remove option combination from the data frame incase they will be removed by feature selection

    if par['isTest'] == False:
        df_data_new = LinearSVC(C = par['C'], penalty = par['penalty'], dual = par['dual']).fit_transform(df_without_options.values, df_y.values)

        #identify the selected features
        selected_features = []
        for column_new in range(0, df_data_new.shape[1]) :
            for column_old in range(0, len(df_without_options.columns)):
                isEqual = True
                for i in range(0, 100):
                    if df_data_new[i][column_new] != df_without_options.iloc[i, column_old]:
                        isEqual = False
                        break
                if isEqual == True:
                    selected_features.append(column_old)
                    break

    df_trainready = []
    if par['isTest'] == False:
        df_trainready_data_without_options = df_without_options.iloc[:, selected_features]
    else:
        df_trainready_data_without_options = df_without_options.iloc[:, selected_features.iloc[:,0]]
    df_trainready.append(pd.concat([df_trainready_data_without_options, df_options], axis = 1))
    if par['isTest'] == False:
        df_trainready.append(pd.DataFrame(selected_features, index = list(range(len(selected_features))),columns=['feature_column']))
    else:
        df_trainready.append(selected_features)
    df_trainready[0].to_csv('result.csv', index=False)

    return df_trainready

# This method splits 'train_ready' into train/development datasets and stores them
# in files
def split_data_5a(df, par):

    # Form a single data frame by merging data and target
    df_data = df[0]
    df_target = df[1]
    df = pd.concat([df_data, df_target], axis = 1)

    # find number of rows and columns
    num_col = len(df.columns)
    num_row = len(df.index)
    print(num_col, num_row)

    # read the train_ratio
    # it is the ratio of trainset to the whole set
    train_ratio= par['train_ratio']

    # read the random seed
    random.seed(par['seed'])

    # split the data
    # splitting is based on customer ID:
    # train_ratio (e.g., 70%) of customers will be in trainset
    new_customer_flag = True
    train_flag = False
    train_arr = np.zeros(num_row)
    for r in range(num_row):
        if new_customer_flag:
            train_flag = (random.random() < train_ratio)
            new_customer_flag = False
        if train_flag:
            train_arr[r] = 1
        # check the record type column to see whether it is
        # a new customer ID
        if df.iloc[r,num_col-1] == 1:
            new_customer_flag = True
    print(train_arr)

    # split the data into trainset and devset
    # for now, labels are in the last column of trainset and devset
    trainset = df.iloc[train_arr==1,:]
    devset = df.iloc[train_arr==0,:]

    return [trainset, devset]

def model_train_svm_6a(df, par):
    
    trainset = df[0]
    
    # find number of rows and columns
    num_col = len(trainset.columns)
    num_row = len(trainset.index)
    print(num_col, num_row)

    # get the features and labels
    train_feature = trainset.iloc[:, 0:(num_col-1)].values
    train_label = trainset.iloc[:,num_col-1].values
    #print(train_feature)
    #print(train_label)

    #print(train_feature, train_label, test_feature, test_label)
    print('%s train features and targets extracted' % datetime.datetime.now())

    # start to train
    svm_model = svm_train(train_feature, train_label)
    print('%s training completed' % datetime.datetime.now())
    
    models['svm'] = svm_model
    
    return []

def model_test_svm_6b(df, par):
    
    svm_model = models['svm']
    testset = df[0]
    testset_customerid = df[1]

    # find number of rows and columns
    num_col = len(testset.columns)
    num_row = len(testset.index)
    print(num_col, num_row)

    # get the test features and labels
    test_feature = testset.iloc[:, 0:(num_col-1)].values
    #print(test_feature)
    
    # generate the confidence level for each row
    predict_confidence = svm_model.predict_proba(test_feature)
    assert len(predict_confidence) == num_row
    #print(predict_confidence)
    
    # generate the predicted options for each customer ID
    predict_options_df = confidence_evaluate(testset_customerid, testset, predict_confidence)
    print('%s confidence list generated' % datetime.datetime.now())

    if par['mode'] is 'dev':
        # compare the predict_options with the devset1
        devset1 = df[2]
        num_row_devset1 = len(devset1.index)
        num_row_predict_options = len(predict_options_df.index)
        print(num_row_devset1, num_row_predict_options)
        assert num_row_devset1 == num_row_predict_options
        
        num_customer = num_row_devset1
        num_err = 0
        for n in range(num_customer):
            idx = n
            predict_options = predict_options_df.ix[n, 'plan']
            label_options = str(devset1.ix[idx,'A']) + str(devset1.ix[idx,'B']) + str(devset1.ix[idx,'C']) + \
                             str(devset1.ix[idx,'D']) + str(devset1.ix[idx,'E']) + str(devset1.ix[idx,'F']) + \
                             str(devset1.ix[idx,'G'])
            print(predict_options, label_options)
            if not (predict_options == label_options):
                num_err += 1
        
        error_rate = 1.0 * num_err / num_customer
        print('#################')
        print('Formal Evaluation:')
        print('number of mis-predictions: %d, number of test cases(customers): %d, error rate %f, prediction rate %f' \
              % (num_err, num_customer, error_rate, 1-error_rate) )
        print('#################')
            
    elif par['mode'] is 'test':
        # output the final prediction report
        pass
    
    return [predict_options_df]


def main():
    # The following lines do not need tuning in most cases
    steps = {'0a': test_only_0a,
            '1a': read_train_data_1a,
            '1b': read_test_data_1b,
            '2a': filter_records_2a,
            '2b': recode_features_2b,
            '2fy1': summarize_data_2a,
            '2fy2': analyze_2fy,
            '3a': create_static_features_3a,
            '3b': create_dynamic_features_3b,
            '3z': merge_datasets_3z,
            '4a': preprocess_train_4a,
            '4b': feature_selection_4b,
            '5a': split_data_5a,
            '6a': model_train_svm_6a,
            '6b': model_test_svm_6b
            }

    datasets = {None: None}

    for id in exec_seq:
        # read in dataframes from .csv files on disk as needed
        print(id)
        if id in df_to_read:
            if isinstance(df_to_read[id],list):
                for dfName in df_to_read[id]:
                    datasets[dfName] = pd.read_csv('../data/'+dfName+'.csv')
            else:
                datasets[df_to_read[id]] = pd.read_csv('../data/'+df_to_read[id]+'.csv')
        # major loop that calls all the steps in execution sequence
        inputDataframes = lookupDict(datasets,df_in[id])
        if isinstance(df_out[id],list):
            # if we need to output multiple datasets, then the 'steps' function must return a list of dataframe
            retDataframes = steps[id](inputDataframes,pars[id])
            for dfName, df in zip(df_out[id],retDataframes):
                datasets[dfName] = df
        else:
            datasets[df_out[id]] = steps[id](inputDataframes,pars[id])
        # write dataframes to .csv files on disk as needed
        if id in df_to_write:
            print(id)
            if isinstance(df_to_write[id],list):
                for dfName in df_to_write[id]:
                    print(dfName)
                    datasets[dfName].to_csv('../data/'+dfName+'.csv',index=False,float_format='%.4f')
            else:
                print(df_to_write[id])
                #datasets[df_to_write[id]].to_csv('data/'+df_to_write[id]+'.csv',index=False,float_format='%.4f')
                datasets[df_to_write[id]].to_csv('../data/'+df_to_write[id]+'.csv',index=False,float_format='%.4f')
if __name__ == "__main__":
    main()
