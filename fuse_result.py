"""
Utility script to fuse different output files.
"""

import numpy as np
import pandas as pd
import argparse

def read_frame(fname):
    data_np = np.genfromtxt(fname, dtype=str) #读取txt文件，delimiter默认为空白
    if data_np.shape[1] == 4:
	    cols = ['fname', 'sysid', 'key', 'score']
    else:
	    cols = ['fname', 'score']

    df = pd.DataFrame(index=data_np[:,0],data=data_np, columns=cols) #表格数据 行标题cols 列标题自动
    df['score'] = df['score'].astype(np.float32, copy=False)#astype： Cast a numpy array to a specified type.
    return df

def fuse(file_list):
    frames = [read_frame(f) for f in file_list]
    if frames[0].shape[1] == 4:
	    merge_cols = ['fname', 'sysid', 'key']
    else:
	    merge_cols = ['fname']
    result_df = pd.concat(frames).groupby(merge_cols, as_index=False)["score"].mean()
    return result_df
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser('Result Fusion utility')
    parser.add_argument('--input', type=str, nargs='+', required=True)
    parser.add_argument('--output', type=str,required=True)
    args = parser.parse_args()
    print('Processing input files : ', args.input)
    fuse_result =  fuse(args.input)
    fuse_result.to_csv(args.output,  sep=' ', header=False, index=False) #csv逗号分隔符文件
    print('Result saved to {}'.format(args.output))
