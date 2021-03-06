import io
import os
import zipfile
import numpy as np
import pandas as pd
from sklearn import svm
from sklearn import ensemble

NUM_ONES_COL = 'num_ones'
NUM_ALL_COL  = 'num_all'
RISK_COL     = 'risk'

def readZipCSV(dir, fileName):
# TODO: make it a full-fledged data reader applicable to potential Kaggle projects
    baseName = os.path.splitext(fileName)[0]
    return pd.read_csv(io.TextIOWrapper(zipfile.ZipFile(dir+fileName).open(baseName,"rU")))

def printList(aList,format):
    for item in aList:
        #print(format % (item),end="")
        print(format % (item))
    print('\n')

def lookupDict(dict,keys):
    """
    Get a value for a key, or a list of values for a list of keys
    """
    if isinstance(keys,list):
        return [dict.get(k) for k in keys]
    else:
        return dict.get(keys)

def gen1DRiskTable(df,catVarName,targetVarName,targetValue):
    all = df.loc[:,catVarName].value_counts()
    ones = df.loc[df.loc[:,targetVarName]==targetValue,catVarName].value_counts()
    return pd.DataFrame({NUM_ONES_COL:ones,NUM_ALL_COL:all,RISK_COL:ones/all}).fillna(0)

def print1DRiskTable(rt,out):
    #print(rt.sort(RISK_COL,ascending=False).to_string(),file=out)
    print(rt.sort(RISK_COL,ascending=False).to_string())

def genRiskTable(df,catVarNameList,targetVarName):
    """
    Generates a hashtable with keys being the combination of catVarNameList and values being
    the estimated probability that the target is 1, assuming targetVarName is a binary variable.
    Example:
        rt = genRiskTable(df, ['colA','colB'], 'target')
        rt['colA_val1']
    """
    return df.groupby(catVarNameList)[targetVarName].mean()

def genCondProbTable(df,listA,listB):
    """
    Generate a hashtable with keys being the combination of the variables in listA+listB, and
    values being the estimated probability Pr(listA=a|listB=b). Both listA and listB can be
    a list of variable names.
    Example:
        cpt = genCondProbTable(df,['colA1','colA2'],['colB1','colB2'])
        cpt['colA1_val1','colA2_val2','colB1_val1','colB2_val2']
    """
    if not listA:
        print("ERROR: Can't calculate probabilities for an empty list of variables.")
        return None

    totals = df.groupby(listA+listB)[listA[0]].count()
    if listB:
        return totals.groupby(level=listB).apply(lambda s: s.astype(float)/s.sum())
    else:
        return totals/totals.sum()

def genCondProbVar(df,cpt):
    """
    Generate a variable/column based on a conditional probability table. The input dataframe df
    should contain column(s) whose values are keys to the conditional probability table.
    Example:
        aNewVar = genCondProbVar(df, cpt)
        df['anotherNewVar'] = genCondProbVar(df, cpt)
    """
    cols = cpt.index.names
    if len(cols) == 1:
        return df.loc[:,cols].apply(lambda row: cpt.get(row.values))
    elif len(cols) >= 2:
        return df.loc[:,cols].apply(lambda row: cpt.get(tuple(row.values)), axis=1)
    else:
        print("ERROR: Empty conditional probability hash table.")
        return None

def discretize(v,nbins,method="linspace"):
    """
    Transform a continuous variable into a discrete one.
    v is the continuous variable, which can be in the form of a list/numpy ndarray/pandas series.
    nbins is the number of bins v is cut into.
    method can be one of linspace/qcut. Method linspace inserts (nbins-1) cutoff points linearly
    between min and max of v. Method qcut cuts v at its nbins-quantiles.
    Example:
        df["newDiscreteCol"] = discretize(df["oldContinuousCol"],10,"qcut")
    """
    if method == "linspace":
        bins = np.linspace(min(v),max(v),nbins)
        return np.digitize(v,bins)
    elif method == "qcut":
        return pd.qcut(v,nbins).labels
    else:
        print("ERROR: Unrecognized method for discretization.")
        print("discretize(v,nbins,method):")
        print(discretize.__doc__)
        return None

def filterUnmatchedRecord(df, columns):
    """
    author: taku
    Filter out the records that have unmatched customer characteristics (except for "time"
    and "day") compared to the last record for each customer.
    """
    # Commented out by FY. Method last() will carry the last non-missing values forward to rows below.
    #df_benchmark = df.groupby(['customer_ID']).last()
    df_benchmark = df.groupby('customer_ID').agg(lambda x: x.iloc[-1])

    record_num = len(df)
    remove_list = []
    for i in range(record_num):
        customer_id = df.iloc[i]['customer_ID']

        if df.iloc[i]['record_type'] == 1: # if record_type=1 then skip
            continue

        isMatch = True
        for column in columns: #all customer characteristics except for "day" and "time"
            if df.iloc[i][column] != df_benchmark.at[customer_id, column]:
                if pd.isnull(df.iloc[i][column]) and pd.isnull(df_benchmark.at[customer_id, column]):
                    continue
                isMatch = False
                break

        if isMatch == False:
            remove_list.append(i)

    df_filtered = df.drop(df.index[remove_list])
    return df_filtered

def single_model_train(train_feature, train_label, model_input, params=None):

    if model_input == 'svm':
        clf = svm.SVC(probability=True, verbose=True, max_iter=10, kernel='rbf')
        clf.fit(train_feature, train_label)
    elif model_input == 'random_forest':
        #clf = ensemble.RandomForestClassifier(n_estimators=10, criterion='gini', max_depth=None, min_samples_split=2, min_samples_leaf=1, max_features='auto', bootstrap=True, oob_score=False, n_jobs=1, random_state=None, verbose=1, min_density=None, compute_importances=None)
        clf = ensemble.RandomForestClassifier(n_estimators=params['n_estimators'], min_samples_split=params['min_samples_split'], min_samples_leaf=params['min_samples_leaf'],criterion=params['criterion'])
        clf.fit(train_feature, train_label)

    return clf


# this method generate the confidence of each test row:
# input: customerid, test features, confidence list
# output: <customer_ID, plan>
#   customer_IDs should be unique
#   plan is the predicted option combination for this customer
def confidence_evaluate(customerid, features, confidence):

    # safety check
    num_row = len(customerid)
    assert num_row == len(confidence)
    assert num_row == len(features.index)
    assert num_row > 0
    print(num_row, len(confidence), len(features.index))
    #print(confidence)
    #print(customerid)

    # create the predict options
    predict_options_df = {}
    customerid_list = []
    options_list= []

    prev_customerid = customerid.ix[0, 'customer_ID']
    #prev_customerid = customerid.iloc[0]['customer_ID']
    customerid_list.append(prev_customerid)
    max_confidence = -1
    max_confidence_idx = -1
    num_customer = 1
    n = 0
    while True:
        #print('prev_customer_id: %s' % prev_customerid)
        store_options = False
        if n >= num_row:
            store_options = True
        else:
            cur_customerid = customerid.ix[n, 'customer_ID']
            #cur_customerid = customerid.iloc[n]['customer_ID']
            conf = confidence[n][1]
            if cur_customerid == prev_customerid:
                # still the same customer ID, update confidence
                if conf > max_confidence:
                    #print(n, conf, max_confidence, max_confidence_idx)
                    max_confidence = conf
                    max_confidence_idx = n
            else:
                num_customer += 1
                customerid_list.append(cur_customerid)
                prev_customerid = cur_customerid
                store_options = True
        if store_options:
            idx = max_confidence_idx
            #predict_options = str(features.ix[idx,'A']) + str(features.ix[idx,'B']) + str(features.ix[idx,'C']) + \
            #                 str(features.ix[idx,'D']) + str(features.ix[idx,'E']) + str(features.ix[idx,'F']) + \
            #                 str(features.ix[idx,'G'])
            predict_options = ""
            for oi in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
                #predict_options += str( int(features.iloc[idx][oi]) )
                predict_options += str(features.ix[idx, oi])

            #print('idx: %d, n: %d' % (idx+2, n))
            #print(str(features.ix[idx,'A']), str(int(features.iloc[idx]['A'])))
            #print(predict_options)
            options_list.append(predict_options)
            if n >= num_row:
                break
            else:
                max_confidence = conf
                max_confidence_idx = n
        n += 1

    # write into the data frame
    #print(customerid_list)
    #print(predict_options)
    predict_options_df['customer_ID'] = customerid_list
    predict_options_df['plan'] = options_list
    df = pd.DataFrame(predict_options_df)

    return df


def mergeOptionsCol(df):
    """
    Sandy:
    Merge A-G option columns into one new column.
    Return a new data frame with the new column
    """
    merge_col = df['A']*10**6 + df['B']*10**5 + df['C']*10**4 + df['D']*10**3 + df['E']*10**2 + df['F']*10 + df['G']
    merge_col_df = merge_col.to_frame(name = 'option_combine')
    #return pd.concat([df,merge_col_df],axis=1)
    return merge_col_df

def filterDuplicate(df):
    """
    Sandy:
    Filter duplicate records based on the column "is_Duplicate"
    """
    t = df.loc[:, 'is_Duplicate']
    return df[t==0]

def handleMissing(df, missing_choice):
    """
    sandy: handle the missing value
    """
    #print(missing_choice)

    filtered_train = pd.DataFrame([])
    #if cmp(missing_choice, '1') == 0:
    if missing_choice == '1':
        print('par_missing == 1')
        filtered_train = df.dropna(axis=0) # drop rows with NA
    #elif cmp(missing_choice, '2') == 0:
    elif missing_choice == '2':
        filtered_train = df.dropna(axis=1) # drop columns with NA
    #elif cmp(missing_choice, '3') == 0:
    elif missing_choice == '3':
        filtered_train = df.fillna(value = 0) # fill missing value with 0 (this execution is not work now)
    #elif cmp(missing_choice, '4') == 0:
    elif missing_choice == '4':
        filtered_train = df.fillna(df.mean())     # fill missing value with mean

    return filtered_train

def Normalize(df):
    """
    normalize the data
    """
    filtered_train_norm = (df - df.mean()) / (df.max() - df.min())
    return filtered_train_norm

def floatrange(start, stop, step):
    r = start
    output = [r]
    while r < stop - 1e-5:
        r += step
        output.append(r)
    return output

def addSyntheticOptions(df):
    """
    author: taku
    Add synthetic option combinations (all neighboring option combinations of the last quote's) for each 
    customer, in order to address truncation and buy-without-quote issues.
    """
    A_values = [0,1,2]
    B_values = [0,1]
    C_values = [1,2,3,4]
    D_values = [1,2,3]
    E_values = [0,1]
    F_values = [0,1,2,3]
    G_values = [1,2,3,4]
    option_values = []
    option_values.append(A_values)
    option_values.append(B_values)
    option_values.append(C_values)
    option_values.append(D_values)
    option_values.append(E_values)
    option_values.append(F_values)
    option_values.append(G_values)

    customer_max_shopping_point = df.iloc[:,0:1].groupby('customer_ID').count().iloc[:,0]
    customer_num = len(customer_max_shopping_point)
    index_cur = -1
    index_last = -1
    df_new = None
    isFirst = True
    for i in range(customer_num):
        index_last = index_cur
        index_cur += customer_max_shopping_point.iloc[i]
        last_quote_record = df.iloc[index_cur : index_cur + 1,:]
        customer_records = df.iloc[index_last + 1 : index_cur + 1]
        if isFirst == True: 
            df_new = customer_records
            isFirst = False
        else:
            df_new = pd.concat([df_new, customer_records], axis = 0)
    
        index = 0
        for change_opt in ['A','B','C','D','E','F','G']:
            for value in option_values[index]:
                if value == last_quote_record.iloc[0][change_opt]:
                    continue
                else:
                    isFound = False
                    for record_index in range(len(customer_records.index)):
                        customer_record = customer_records.iloc[record_index]
                        isMatch = True
                        for opt in ['A','B','C','D','E','F','G']:
                            if opt == change_opt:
                                if value != customer_record[opt]:
                                    isMatch = False
                                    break
                            else:
                                if last_quote_record.iloc[0][opt] != customer_record[opt]:
                                    isMatch = False
                                    break
                        if isMatch == True:
                            isFound = True
                            break
                    if isFound != True:
                        synthetic_record = last_quote_record.copy(deep = True)
                        for opt in ['A','B','C','D','E','F','G']:
                            if opt == change_opt:
                                synthetic_record.loc[:,opt] = value
                        df_new = pd.concat([df_new, synthetic_record], axis = 0) 
            index += 1
    return df_new
