#!/usr/bin/env python3
# Copyright (c) 2013 Spotify AB
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

try:
    import coverage
except ImportError:
    pass
import sys
import unittest
import os

def main():
    #Cleanup old html report:
    for root, dirs, files in os.walk('test/output_coverage_html/'):
        for f in files:
            if f == '.gitignore' or f == '.empty_dir':
                continue
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

    #Perform coverage analisys:
    if "coverage" in sys.modules:
        cov = coverage.coverage()
        cov.start()

    #Discover the tests and execute them:
    loader = unittest.TestLoader()
    tests = loader.discover('./test/')
    testRunner = unittest.runner.TextTestRunner(descriptions=True, verbosity=1)
    testRunner.run(tests)

    if "coverage" in sys.modules:
        cov.stop()
        cov.html_report()

if __name__ == '__main__':
    main()
