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

import pickle

PHONES_FILE = 'phones.pkl'

with open(PHONES_FILE, 'rb') as f:
  charset = [' '] + list(pickle.load(f))
C2IX_DICT = {charset[i]: i for i in range(len(charset))}
IX2C_DICT = {v: k for k, v in C2IX_DICT.items()}

SIZE = len(charset)


def letter_to_id(letter):
  """
  Converts `letter` to vocabulary id

  Args:
    letter: letter to convert, allowed is a-z and space

  Returns: the vocabulary encoded letter

  """
  return C2IX_DICT[letter]


def id_to_letter(identifier):
  """
  Converts the vocabulary encoded letter `identifier` to its character representation

  Args:
    identifier: encoded letter to decode

  Returns: the character letter

  """
  return IX2C_DICT[identifier]


def sentence_to_ids(sentence):
  """
  Convert a string `sentence` to its encoded representation

  Args:
    sentence: sentence of type string

  Returns: list of ints (encoded characters)

  """
  return [letter_to_id(letter) for letter in sentence]


def ids_to_sentence(identifiers):
  """
  Convert an complete list of encoded characters `identifiers` to their character representation

  Args:
    identifiers:  list of ints (encoded characters)

  Returns: decoded sentence as string

  """
  return ''.join(id_to_letter(identifier) for identifier in identifiers)
