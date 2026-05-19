"""
   Copyright 2022 Thomas Reidemeister

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   ----
   Vendored from https://github.com/treideme/brother_pt at commit
   b7f0f1786818920a6b51cdb0e5ad4a09b035f670 (dev branch). Vendored to avoid
   the upstream `Pillow==8.4.0` hard pin which conflicts with brother_ql2's
   Pillow >=10.0.0 requirement. Local modification: this file re-exports the
   public API at the package level so callers can `from vendor.brother_pt
   import BrotherPt, find_printers` regardless of upstream's CLI-first layout.
"""
from .printer import BrotherPt, find_printers  # noqa: F401

VERSION = "1.0"
