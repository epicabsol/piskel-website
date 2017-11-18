from base import BaseHandler
import models
import json
from markdown import markdown
from jinja2 import Markup


# Handler dedicated to rendering markdown docs pages
class DocsHandler(BaseHandler):
    def markdownify(self, filename):
        input_text = ''
        with open('docs/' + filename) as file:
            input_text = file.read()
        return markdown(input_text)

    def mdpage(self, filename, values):
        values.update({'mdcontent': Markup(self.markdownify(filename))})
        self.render('docs/docs.html', values)

class DocsIndexHandler(DocsHandler):
    def get(self):
        self.mdpage('index.md', { })

class DocsItemHandler(DocsHandler):
    def get(self, section, item):
        # HACK: Sanitization needed?
        self.mdpage(section + '/' + item + '.md', { })