#!/usr/bin/env python
import os
from optparse import OptionParser

from jinja2 import Template


TEMPLATE = open(os.path.join(os.path.dirname(__file__), 'crontab.tpl')).read()


def main():
    parser = OptionParser()
    parser.add_option("-z", "--zamboni",
                      help="Location of zamboni (required)")
    parser.add_option("-r", "--remora",
                      help="Location of remora bin dir (required)")
    parser.add_option("-u", "--user",
                      help=("Prefix cron with this user. "
                           "Only define for cron.d style crontabs"))
    parser.add_option("-p", "--python", default="/usr/bin/python2.6",
                      help="Python interpreter to use")

    (opts, args) = parser.parse_args()

    if not opts.zamboni or not opts.remora:
        parser.error("-z and -r must be defined")

    ctx = {'django': 'cd %s; %s manage.py' % (opts.zamboni, opts.python),
           'remora': 'cd %s' % opts.remora}
    ctx['z_cron'] = '%s cron' % ctx['django']

    if opts.user:
        for k, v in ctx.iteritems():
            ctx[k] = '%s %s' % (opts.user, v)

    # Needs to stay below the opts.user injection.
    ctx['python'] = opts.python

    print Template(TEMPLATE).render(**ctx)


if __name__ == "__main__":
    main()
