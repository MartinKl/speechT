# Copyright 2016 Louis Kirsch. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from functools import partial
from multiprocessing.pool import Pool

import librosa
import os

import logging

import multiprocessing
import numpy as np
import fnmatch
import random
import vocabulary
import corpus
import argparse


def normalize(values):
  """
  Normalize values to mean 0 and std 1
  """
  return (values - np.mean(values)) / np.std(values)


def calc_power_spectrogram(audio_data, samplerate, n_mels=257, n_fft=400, hop_length=160):
  """
  Calculate power spectrogram from the given raw audio data

  Args:
    audio_data: numpyarray of raw audio wave
    samplerate: the sample rate of the `audio_data`
    n_mels: the number of mels to generate
    n_fft: the window size of the fft
    hop_length: the hop length for the window

  Returns: the spectrogram in the form [time, n_mels]

  """
  spectrogram = librosa.feature.melspectrogram(audio_data, sr=samplerate, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length)

  # convert to log scale (dB)
  log_spectrogram = librosa.logamplitude(spectrogram, ref_power=np.max)

  # normalize
  normalized_spectrogram = normalize(log_spectrogram)

  return normalized_spectrogram.T


def calc_mfccs(audio_data, samplerate, n_mfcc=13, n_fft=400, hop_length=160):
  """
  Calculate mfcc coefficients from the given raw audio data

  Args:
    audio_data: numpyarray of raw audio wave
    samplerate: the sample rate of the `audio_data`
    n_mfcc: the number of coefficients to generate
    n_fft: the window size of the fft
    hop_length: the hop length for the window

  Returns: the mfcc coefficients in the form [time, coefficients]

  """
  mfcc = librosa.feature.mfcc(audio_data, sr=samplerate, n_mfcc=n_mfcc, n_fft=n_fft, hop_length=hop_length)

  # add derivatives and normalize
  mfcc_delta = librosa.feature.delta(mfcc)
  mfcc_delta2 = librosa.feature.delta(mfcc, order=2)
  mfcc = np.concatenate((normalize(mfcc),
                         normalize(mfcc_delta),
                         normalize(mfcc_delta2)), axis=0)

  return mfcc.T


def iglob_recursive(directory, file_pattern):
  """
  Recursively search for `file_pattern` in `directory`

  Args:
    directory: the directory to search in
    file_pattern: the file pattern to match (wildcard compatible)
    followlinks: follow symbolic links in file iteration

  Returns: iterator for found files

  """
  for root, dir_names, file_names in os.walk(directory, followlinks=True):
    files = fnmatch.filter(file_names, file_pattern)
    for filename in files:
      yield os.path.join(root, filename)


class SpeechCorpusReader:
  """
  Reads preprocessed speech corpus to be used by the NN
  """
  def __init__(self, data_directory):
    """
    Create SpeechCorpusReader and read samples from `data_directory`

    Args:
      data_directory: the directory to use
    """
    self._data_directory = data_directory
    self._transcript_dict_cache = None

  @property
  def _transcript_dict(self):
    if not self._transcript_dict_cache:
      self._transcript_dict_cache = self._build_transcript()
    return self._transcript_dict_cache

  @staticmethod
  def _get_transcript_entries(transcript_directory):
    """
    Iterate over all transcript lines and yield splitted entries

    Args:
      transcript_directory: open all transcript files in this directory and extract their contents

    Returns: Iterator for all entries in the form (id, sentence)

    """
    transcript_files = iglob_recursive(transcript_directory, '*.trans.txt')
    for transcript_file in transcript_files:
      with open(transcript_file, 'r') as f:
        for line in f:
          # Strip included new line symbol
          line = line.rstrip('\n')

          # Each line is in the form
          # 00-000000-0000 WORD1 WORD2 ...
          splitted = line.split(' ', 1)
          yield splitted

  @staticmethod
  def _fix_transcript_dir(directory):
      print('fixing', directory)
      return directory.replace('LibriSpeech', 'export/LibriSpeechPhones')

  def _build_transcript(self):
    """
    Builds a transcript from transcript files, mapping from audio-id to a list of vocabulary ids

    Returns: the created transcript
    """

    # Create the transcript dictionary
    transcript_dict = dict()
    for splitted in self._get_transcript_entries(self._data_directory):
      transcript_dict[splitted[0]] = vocabulary.sentence_to_ids(splitted[1])

    return transcript_dict

  @classmethod
  def _extract_audio_id(cls, audio_file):
    file_name = os.path.basename(audio_file)
    audio_id = os.path.splitext(file_name)[0]

    return audio_id

  @classmethod
  def _transform_sample(cls, audio_file, preprocess_fnc):
    audio_data, samplerate = librosa.load(audio_file)
    audio_fragments = preprocess_fnc(audio_data, samplerate)
    audio_id = cls._extract_audio_id(audio_file)

    return audio_id, audio_fragments

  @classmethod
  def _transform_and_store_sample(cls, audio_file, preprocess_fnc, transcript, out_directory):
    audio_id, audio_fragments = cls._transform_sample(audio_file, preprocess_fnc)
    np.savez(out_directory + '/' + audio_id, audio_fragments=audio_fragments, transcript=transcript)

  def generate_samples(self, directory, preprocess_fnc):
    """
    Generates samples from the given directory

    Args:
      directory: the sub-directory of the initial data directory to sample from
      preprocess_fnc: the preprocessing function to use

    Returns: generator with (audio_id: string, audio_fragments: ndarray, transcript: list(int)) tuples

    """
    audio_files = list(iglob_recursive(self._data_directory + '/' + directory, '*.flac'))
    print('audio files for transcripts: ', len(audio_files))
    transcript_dict = self._transcript_dict

    for audio_file in audio_files:
      audio_id, audio_fragments = self._transform_sample(audio_file, preprocess_fnc)
      yield audio_id, audio_fragments, transcript_dict[audio_id]

  def _get_directory(self, feature_type, sub_directory):
    preprocess_directory = 'preprocessed'
    if feature_type == calc_power_spectrogram or feature_type == 'power':
      preprocess_directory += '-power'

    directory = os.path.join(self._data_directory, preprocess_directory, sub_directory)

    return directory

  def store_samples(self, directory, preprocess_fnc):
    """
    Read audio files from `directory` and store the preprocessed version in preprocessed/`directory`

    Args:
      directory: the sub-directory to read from
      preprocess_fnc: The preprocessing function to use

    """
    print('Called with', directory)
    out_directory = self._get_directory(preprocess_fnc, directory)
    print('Outdir', out_directory)
    if not os.path.exists(out_directory):
      os.makedirs(out_directory)

    audio_files = list(iglob_recursive(os.path.join(self._data_directory, directory), '*.flac'))
    with open('inspect.txt') as f:
        f.write(os.linesep.join(audio_files))
    raise NotImplementedError
    print('audio files:', len(audio_files), 'from', os.path.join(self._data_directory, directory))
    with Pool(processes=multiprocessing.cpu_count()) as pool:

      transcript_dict = self._transcript_dict

      for audio_file in audio_files:
        audio_id = self._extract_audio_id(audio_file)
        transcript_entry = transcript_dict[audio_id]
        transform_args = (audio_file, preprocess_fnc, transcript_entry, out_directory)
        pool.apply_async(SpeechCorpusReader._transform_and_store_sample, transform_args)

      pool.close()
      pool.join()

  def load_samples(self, directory, max_size=False, loop_infinitely=False, limit_count=0, feature_type='mfcc'):
    """
    Load the preprocessed samples from `directory` and return an iterator

    Args:
      directory: the sub-directory to use
      max_size: the maximum audio time length, all others are discarded (default: False)
      loop_infinitely: after one pass, shuffle and pass again (default: False)
      limit_count: maximum number of samples to use, 0 equals unlimited (default: 0)
      feature_type: features to use 'mfcc' or 'power'

    Returns: iterator for samples (audio_data, transcript)

    """

    load_directory = self._get_directory(feature_type, directory)

    if not os.path.exists(load_directory):
      raise ValueError('Directory {} does not exist'.format(load_directory))

    files = list(iglob_recursive(load_directory, '*.npz'))
    random.shuffle(files)

    if limit_count:
      files = files[:limit_count]

    while True:
      for file in files:
        with np.load(file) as data:
          audio_length = data['audio_fragments'].shape[0]
          if not max_size or audio_length <= max_size:
            yield data['audio_fragments'], data['transcript']
          else:
            logging.warning('Audio snippet too long: {}'.format(audio_length))
      if not loop_infinitely:
        break
      random.shuffle(files)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description='Generate preprocessed file from audio files and transcripts')
  parser.add_argument('--data_directory', type=str, required=False, default='data',
                      help='The data directory to pull the files from and store the preprocessed file')
  parser.add_argument('--all', required=False, default=False, action='store_true',
                      help='Preprocess training, test and development data')
  parser.add_argument('--train', required=False, default=False, action='store_true',
                      help='Preprocess training data')
  parser.add_argument('--test', required=False, default=False, action='store_true',
                      help='Preprocess test data')
  parser.add_argument('--dev', required=False, default=False, action='store_true',
                      help='Preprocess development data')
  parser.add_argument('--power-spectrogram', dest='preprocess_fnc', action='store_const',
                      const=calc_power_spectrogram, default=calc_mfccs,
                      help='Generate power spectrograms instead of mfccs')
  args = parser.parse_args()

  if not(args.all or args.train or args.test or args.dev):
    print('You must specify the data set to preprocess. Use --help')

  corp = corpus.SpeechCorpusProvider(args.data_directory)
  corp.ensure_availability()
  corpus_reader = SpeechCorpusReader(args.data_directory)

  if args.all or args.train:
    print('Preprocessing training data')
    corpus_reader.store_samples('train', args.preprocess_fnc)

  if args.all or args.test:
    print('Preprocessing test data')
    corpus_reader.store_samples('test', args.preprocess_fnc)

  if args.all or args.dev:
    print('Preprocessing development data')
    corpus_reader.store_samples('dev', args.preprocess_fnc)
