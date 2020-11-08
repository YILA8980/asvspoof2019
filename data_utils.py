"""
    Author: Moustafa Alzantot (malzantot@ucla.edu)
    All rights reserved.
"""
import torch
import collections
import os
import soundfile as sf
import librosa
from torch.utils.data import DataLoader, Dataset
import numpy as np
from joblib import Parallel, delayed
import h5py

LOGICAL_DATA_ROOT = '/data/zjuyeh/tmptest/LA'
PHISYCAL_DATA_ROOT = '/data/zjuyeh/tmptest/PA'

ASVFile = collections.namedtuple('ASVFile',
    ['speaker_id', 'file_name', 'path', 'sys_id', 'key'])

class ASVDataset(Dataset):
    """ Utility class to load  train/dev datatsets """
    def __init__(self, transform=None, 
        is_train=True, sample_size=None, 
        is_logical=True, feature_name=None, is_eval=False): 
        # 删除eval_part参数
    
        self.sysid_dict = {
            # known types (eg: PA_0077 PA_D_0029677 ccc CC spoof)
            # For LA:
            '-': 0,  # bonafide speech
            'A01': 1, # Wavenet vocoder
            'A02': 2, # Conventional vocoder WORLD
            'A03': 3, # Conventional vocoder MERLIN
            'A04': 4, # Unit selection system MaryTTS
            'A05': 5, # Voice conversion using neural networks
            'A06': 6, # transform function-based voice conversion
            # For PA:
            'AA':7,
            'AB':8,
            'AC':9,
            'BA':10,
            'BB':11,
            'BC':12,
            'CA':13,
            'CB':14,
            'CC': 15
        }
        self.sysid_dict_inv = {v:k for k,v in self.sysid_dict.items()}

        # 文件名
        # LA/ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.dev.trl.txt txt内存储flac文件名 音频信息 标签
        # LA/ASVspoof2019_LA_dev/flac/ 存储具体音频文件
        if is_logical:
            data_root = LOGICAL_DATA_ROOT
            track = 'LA'
        else:
            data_root = PHISYCAL_DATA_ROOT
            track = 'PA'
        assert feature_name is not None, 'must provide feature name'
        self.track = track
        self.is_logical = is_logical
        self.prefix = 'ASVspoof2019_{}'.format(track)
        '''
        v1_suffix = ''
        if is_eval and track == 'PA':
            v1_suffix='_v1'
        '''
        self.is_eval = is_eval
        self.data_root = data_root

        self.dset_name = 'eval' if is_eval else 'train' if is_train else 'dev'
        # files_dir文件名组合完成
        self.files_dir = os.path.join(self.data_root, '{}_{}'.format(self.prefix, self.dset_name ), 'flac') 

        self.protocols_fname = 'eval.trl' if is_eval else 'train.trn' if is_train else 'dev.trl'
        self.protocols_dir = os.path.join(self.data_root,'{}_cm_protocols/'.format(self.prefix))
        # protocols_fname文件名组合完成
        self.protocols_fname = os.path.join(self.protocols_dir,
            'ASVspoof2019.{}.cm.{}.txt'.format(track, self.protocols_fname)) 
        # parse_protocols_file函数传入参数protocols_fname，open(protocols_fname).readlines，
        #  _parse_line函数对lines进行map，return ASVFile函数结果，函数用到self.files_dir


        # get data 
        # [self.data_x, self.data_y, self.data_sysid, self.files_meta]
        self.cache_fname = 'cache_{}_{}_{}.npy'.format(self.dset_name, track, feature_name)
        self.cache_matlab_fname = 'cache_{}_{}_{}.mat'.format(self.dset_name, track, feature_name)
        self.transform = transform
        if os.path.exists(self.cache_fname): #已经存在.npy 直接读取有效数据
            self.data_x, self.data_y, self.data_sysid, self.files_meta = torch.load(self.cache_fname)
            print('Dataset loaded from cache ', self.cache_fname)
        elif feature_name == 'cqcc':
            if os.path.exists(self.cache_matlab_fname):
                self.data_x, self.data_y, self.data_sysid = self.read_matlab_cache(self.cache_matlab_fname)
                self.files_meta = self.parse_protocols_file(self.protocols_fname)
                
                print('Dataset loaded from matlab cache ', self.cache_matlab_fname)
                torch.save((self.data_x, self.data_y, self.data_sysid, self.files_meta),
                           self.cache_fname, pickle_protocol=4)
                print('Dataset saved to cache ', self.cache_fname)
            else:
                print("Matlab cache for cqcc feature do not exist.")
        else:#不存在.npy 从原始文件读取数据 并保存有效数据为.npy
            self.files_meta = self.parse_protocols_file(self.protocols_fname)
            data = list(map(self.read_file, self.files_meta))
            self.data_x, self.data_y, self.data_sysid = map(list, zip(*data))
            if self.transform:
                # self.data_x = list(map(self.transform, self.data_x)) 
                self.data_x = Parallel(n_jobs=4, prefer='threads')(delayed(self.transform)(x) for x in self.data_x)
            torch.save((self.data_x, self.data_y, self.data_sysid, self.files_meta), self.cache_fname)
            print('Dataset saved to cache ', self.cache_fname)

        # 每次选择 sample_size
        if sample_size:
            select_idx = np.random.choice(len(self.files_meta), size=(sample_size,), replace=True).astype(np.int32)
            self.files_meta= [self.files_meta[x] for x in select_idx]
            self.data_x = [self.data_x[x] for x in select_idx]
            self.data_y = [self.data_y[x] for x in select_idx]
            self.data_sysid = [self.data_sysid[x] for x in select_idx]
        self.length = len(self.data_x)

    def __len__(self):
        return self.length

    def __getitem__(self, idx):
        x = self.data_x[idx]
        y = self.data_y[idx]
        return x, y, self.files_meta[idx]

    def read_file(self, meta):
        data_x, sample_rate = sf.read(meta.path)
        data_y = meta.key
        return data_x, float(data_y), meta.sys_id

    def _parse_line(self, line): #对每一行进行语义分析
        tokens = line.strip().split(' ')
        if self.is_eval:
            return ASVFile(speaker_id=tokens[0],
                file_name=tokens[1],
                path=os.path.join(self.files_dir, tokens[1] + '.flac'),
                sys_id=0, #应该添加字典吧？
                key=int(tokens[4] == 'bonafide'))
        return ASVFile(speaker_id=tokens[0],
            file_name=tokens[1],
            path=os.path.join(self.files_dir, tokens[1] + '.flac'),
            sys_id=self.sysid_dict[tokens[3]],
            key=int(tokens[4] == 'bonafide'))

    def parse_protocols_file(self, protocols_fname):
        lines = open(protocols_fname).readlines()
        files_meta = map(self._parse_line, lines) 
        #files_meta：由ASVFile ['speaker_id', 'file_name', 'path', 'sys_id', 'key']构成的数组
        return list(files_meta)

    def read_matlab_cache(self, filepath):
        f = h5py.File(filepath, 'r')
        # filename_index = f["filename"]
        # filename = []
        data_x_index = f["data_x"]
        sys_id_index = f["sys_id"]
        data_x = []
        data_y = f["data_y"][0]
        sys_id = []
        for i in range(0, data_x_index.shape[1]):
            idx = data_x_index[0][i]  # data_x
            temp = f[idx]
            data_x.append(np.array(temp).transpose())
            # idx = filename_index[0][i]  # filename
            # temp = list(f[idx])
            # temp_name = [chr(x[0]) for x in temp]
            # filename.append(''.join(temp_name))
            idx = sys_id_index[0][i]  # sys_id
            temp = f[idx]
            sys_id.append(int(list(temp)[0][0]))
        data_x = np.array(data_x)
        data_y = np.array(data_y)
        return data_x.astype(np.float32), data_y.astype(np.int64), sys_id


# if __name__ == '__main__':
#    train_loader = ASVDataset(LOGICAL_DATA_ROOT, is_train=True)
#    assert len(train_loader) == 25380, 'Incorrect size of training set.'
#    dev_loader = ASVDataset(LOGICAL_DATA_ROOT, is_train=False)
#    assert len(dev_loader) == 24844, 'Incorrect size of dev set.'

