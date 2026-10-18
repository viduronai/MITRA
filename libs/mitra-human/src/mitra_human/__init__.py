"""mitra-human: make the AI sound like a real Indian telecaller.

TODO: native-speaker review for hi/te tables.
"""

from __future__ import annotations

from mitra_human._lang import Lang
from mitra_human._phone import spell_phone
from mitra_human.backchannel import BackchannelPolicy
from mitra_human.filler import FillerPolicy, Gender
from mitra_human.honorific import Formality, HonorificGender, honorific
from mitra_human.numwords import number_to_words
from mitra_human.speakable import speakable, spell_digits, spell_email
from mitra_human.truncate import truncate_to_heard

__all__ = [
    "BackchannelPolicy",
    "FillerPolicy",
    "Formality",
    "Gender",
    "HonorificGender",
    "Lang",
    "honorific",
    "number_to_words",
    "speakable",
    "spell_digits",
    "spell_email",
    "spell_phone",
    "truncate_to_heard",
]
