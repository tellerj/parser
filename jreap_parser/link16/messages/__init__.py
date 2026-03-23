"""J-series message decoders — extract tactical data from raw J-words.

Each decoder handles exactly one (label, sublabel) pair and satisfies the
``MessageDecoder`` protocol defined in ``core/interfaces.py``.

How to add a new message decoder
=================================

1. Create a new module in this package (e.g. ``j7_0.py`` for J7.0).

2. Write a class with four members that match the ``MessageDecoder``
   protocol::

       from jreap_parser.core.types import Link16Message, RawJWord

       LABEL = 7
       SUBLABEL = 0

       class J70DataUpdateDecoder:
           @property
           def label(self) -> int:
               return LABEL

           @property
           def sublabel(self) -> int:
               return SUBLABEL

           @property
           def msg_type_name(self) -> str:
               return "J7.0 Track Management"

           def decode(self, words: list[RawJWord]) -> Link16Message | None:
               if not words:
                   return None
               initial = words[0]
               # Decode fields from the 70-bit FWF data portion.
               # Populate a Link16Message with whatever you can extract.
               return Link16Message(
                   msg_type="J7.0",
                   stn=initial.stn,
                   timestamp=initial.timestamp,
               )

   No base class or inheritance needed — just match the method signatures.

3. Register it in ``__main__.py`` inside ``build_jword_parser()``::

       from jreap_parser.link16.messages.j7_0 import J70DataUpdateDecoder
       parser.register(J70DataUpdateDecoder())

   That's it. The ``JWordParser`` will automatically route any J-word with
   the matching (label, sublabel) to your decoder.

4. Write a test in ``tests/`` that constructs known J-words and asserts
   the correct ``Link16Message`` output.

Important: MIL-STD-6016 boundary
=================================

The J-word *envelope* (word format, label, sublabel, MLI — bits 0-12) is
publicly documented. Everything inside the 57-bit message-specific data
portion (bits 13-69) is defined in MIL-STD-6016 and is *not* public.

Current decoders are stubs that extract the envelope but leave the
message-specific fields as ``None``. Once MIL-STD-6016 access is obtained,
fill in the bit-field extraction logic inside each decoder's ``decode()``
method — no other modules need to change.

Existing implementations
========================

- ``j2_2.py``  — J2.2 Air PPLI (stub — awaiting MIL-STD-6016).
- ``j3_2.py``  — J3.2 Air Track (stub — awaiting MIL-STD-6016).
- ``j28_2.py`` — J28.2 Free Text (stub — awaiting MIL-STD-6016).
"""
