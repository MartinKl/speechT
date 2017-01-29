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
import os
import tarfile
import urllib.request


class SpeechCorpusProvider:
  """
  Ensures the availability and downloads the speech corpus if necessary
  """

  TRAIN_DIR = 'train'  # FIXME
  DEV_DIR = 'dev'
  TEST_DIR = 'test'

  DEV_CLEAN_SET = 'dev-clean'
  TRAIN_CLEAN_100_SET = 'train-clean-100'
  TRAIN_CLEAN_360_SET = 'train-clean-360'
  TRAIN_OTHER_500_SET = 'train-other-500'
  TEST_CLEAN_SET = 'test-clean'
  DATA_SETS = {
    (DEV_DIR, DEV_CLEAN_SET),
    (TRAIN_DIR, TRAIN_CLEAN_100_SET),
    (TRAIN_DIR, TRAIN_CLEAN_360_SET),
    (TRAIN_DIR, TRAIN_OTHER_500_SET),
    (TEST_DIR, TEST_CLEAN_SET)
  }


  def __init__(self, data_directory):
    """
    Creates a new SpeechCorpusProvider with the root directory `data_directory`.
    The speech corpus is downloaded and extracted into sub-directories.

    Args:
      data_directory: the root directory to use, e.g. data/
    """

    self._data_directory = data_directory
    self._make_dir_if_not_exists(data_directory)
    self._make_dir_if_not_exists(os.path.join(
      data_directory, SpeechCorpusProvider.DEV_DIR))
    self._make_dir_if_not_exists(os.path.join(
      data_directory, SpeechCorpusProvider.TRAIN_DIR))

  @staticmethod
  def _make_dir_if_not_exists(directory):
    """
    Helper function to create a directory if it doesn't exist.

    Args:
      directory: directory to create
    """

    if not os.path.exists(directory):
      os.makedirs(directory)

  def _download_if_not_exists(self, remote_file_name):
    """
    Downloads the given `remote_file_name` if not yet stored in the `data_directory`

    Args:
      remote_file_name: the file to download

    Returns: path to downloaded file
    """

    raise NotImplementedError(remote_file_name)

  @staticmethod
  def _extract_from_to(tar_file_name, source, target_directory):
    """
    Extract all necessary files `source` from `tar_file_name` into `target_directory`

    Args:
      tar_file_name: the tar file to extract from
      source: the directory in the root to extract
      target_directory: the directory to store the files in
    """

    raise NotImplementedError('{}->{}'.format(source, target_directory))

  def _is_ready(self, data_sets=DATA_SETS):
    """
    Returns whether all `data_sets` are downloaded and extracted

    Args:
      data_sets: list of the datasets to ensure

    Returns: bool, is ready to use

    """

    data_set_paths = [os.path.join(set_type, set_name)
                      for set_type, set_name in data_sets]
    return all([os.path.exists(os.path.join(
      self._data_directory, data_set
    )) for data_set in data_set_paths])

  def _download(self, data_sets=DATA_SETS):
    """
    Download the given `data_sets`

    Args:
      data_sets: a list of the datasets to download
    """

    raise NotImplementedError(data_sets)

  def _extract(self, data_sets=DATA_SETS):
    """
    Extract all necessary files from the given `data_sets`

    Args:
      data_sets: a list of the datasets to extract the files from
    """

    raise NotImplementedError

  def ensure_availability(self, test_only=False):
    """
    Ensure that all datasets are downloaded and extracted. If this is not the case,
    the download and extraction is initated.

    Args:
      test_only: Whether to exclude training and development data
    """

    if test_only:
      data_sets = [(SpeechCorpusProvider.TEST_DIR, SpeechCorpusProvider.TEST_CLEAN_SET)]
    else:
      data_sets = SpeechCorpusProvider.DATA_SETS

