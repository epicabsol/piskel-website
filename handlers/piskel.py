import webapp2, logging
import models

from models import Framesheet, Piskel
from google.appengine.ext import db
from webapp2_extras import jinja2
from base import BaseHandler
from handlers import image as image_handler

_ANONYMOUS_USER = long(100000001)

class PiskelHandler(BaseHandler):
  def _authorize(self, piskel):   
    if self.is_logged_in:
      if self.session_user['user_id'] == piskel.owner:
        return True
    return False

  def _authorize_for_view(self, piskel):   
    return self._authorize(piskel) or not piskel.private

  def _authorize_for_clone(self, piskel):   
    return self.is_logged_in and not piskel.private

  def _get_logged_user_id(self):
    if self.is_logged_in:
      user = self.current_user
      user.put()
      return self.session_user['user_id']

  def create(self):
    user_id = self._get_logged_user_id() or _ANONYMOUS_USER
    piskel = Piskel(owner=user_id)
    piskel.garbage = True
    piskel.put()

    self.redirect('/p/'+str(piskel.key()) + '/edit')

  def edit(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize_for_view(piskel):
      framesheet = piskel.get_current_framesheet()
      if framesheet:
        content = framesheet.content
        fps = framesheet.fps
      else:
        content = 'null'
        fps = 12
        
      values = {
        'user': self.current_user if self.is_logged_in else False,
        'piskel_id' : piskel_id,
        'piskel_content' : content,
        'piskel_fps' : fps,
        'piskel': piskel,
        'is_logged_in': self.is_logged_in
      }

      self.render("editor.html", values)
    else:
      self.abort(403)

  def _clone_piskel(self, piskel, user_id):
    clone = Piskel(owner=user_id)
    clone.garbage = False
    clone.name = piskel.name + " clone"
    if piskel.description:
      clone.description = "(copied from original) " + piskel.description
    return clone

  def clone(self, piskel_id):
    piskel = db.get(piskel_id)
    valid_for_clone = piskel and piskel.get_current_framesheet()
    if valid_for_clone:
      if self._authorize_for_clone(piskel):
        user_id = self.session_user['user_id']
        
        clone = self._clone_piskel(piskel, user_id)
        clone.put()
        clone_id = str(clone.key())

        active_framesheet = piskel.get_current_framesheet()
        framesheet = active_framesheet.clone(clone_id)
        clone.set_current_framesheet(framesheet)

        # trigger refresh
        db.get(framesheet.key())

        self.redirect('/p/' + clone_id + '/view')
      else:
        self.abort(403)
    else:
      self.abort(404)   

  def _get_piskel_details(self, piskel):
    framesheets = piskel.get_framesheets()
    return {
      # mandatory
      'user': self.current_user if self.is_logged_in else False,
      'session': self.session_user if self.is_logged_in else False,
      'is_logged_in': self.is_logged_in,
      # page-specific
      'is_author': self.is_logged_in and long(piskel.owner) == self.session_user['user_id'],
      'piskel_id' : piskel.key(),
      'framesheets' : framesheets,
      'piskel': piskel.prepare_for_view(),
      'owner': self.get_user(piskel.owner)
    }

  def get_history(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize(piskel):
      values = self._get_piskel_details(piskel)
      self.render("piskel/piskel-history.html", values)
    else:
      self.abort(403)

  def rollback_piskel_to_framesheet (self, piskel_id, framesheet_id):
    piskel = db.get(piskel_id)
    framesheet = db.get(framesheet_id)
    valid = piskel and framesheet
    if valid:
      if self._authorize(piskel):
        piskel.set_current_framesheet(framesheet.clone(), True)
        self.redirect('/p/' + piskel_id + '/history')

  def view(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize_for_view(piskel):
      values = self._get_piskel_details(piskel)
      self.render("piskel/piskel-details.html", values)
    else:
      self.abort(403)

  def permanently_delete(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize(piskel):
      piskel.delete()
      db.get(piskel_id) # funny looks like this forces 
      self.redirect(self.request.get('callback_url'))
    else:
      self.abort(403)

  def delete(self, piskel_id):
    self._update_delete_status(piskel_id, True, self.request.get('callback_url'))

  def restore(self, piskel_id):
    self._update_delete_status(piskel_id, False, self.request.get('callback_url'))

  def _update_delete_status(self, piskel_id, status, redirect_url):
    piskel = db.get(piskel_id)
    if self._authorize(piskel):
      piskel.deleted = status
      piskel.put()

      # force consistency
      db.get(piskel_id) 

      self.redirect(redirect_url)
    else:
      self.abort(403)

  def updateinfo(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize(piskel):
      post_data = self.request.POST
      piskel.name = post_data.get('name')
      piskel.description = post_data.get('description')
      piskel.private = not bool(post_data.get('public'))
      piskel.put()

      # consistency will be forced by get made on view(self)
      self.redirect('/p/' + piskel_id + '/view')
    else:
      self.abort(403)

  # Save a new framesheet on an existing piskel
  def save(self, piskel_id):
    piskel = db.get(piskel_id)
    if self._authorize(piskel):
      post_data = self.request.POST

      content = post_data.get('framesheet_content')
      fps = post_data.get('fps_speed')
      frames = long(post_data.get('frames'))

      preview_link=image_handler.create_link(post_data.get('preview'))
      framesheet_link=image_handler.create_link(post_data.get('framesheet'))

      framesheet = Framesheet(
        piskel_id=piskel_id, 
        fps=fps, 
        content=content, 
        frames=frames, 
        preview_link=preview_link, 
        framesheet_link=framesheet_link,
        active=True
      )

      piskel.set_current_framesheet(framesheet)

      piskel.name = post_data.get('name')
      piskel.garbage = False # remove garbage flag to avoid collection by CRON task + enable listing
      piskel.put()
      
      # force consistency
      db.get(piskel_id) 
      
      self.response.out.write(piskel.key())
    else:
      self.abort(403)
