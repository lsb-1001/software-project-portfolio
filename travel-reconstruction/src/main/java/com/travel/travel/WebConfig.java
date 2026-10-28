package com.travel.travel;

import jakarta.servlet.http.*;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.*;

@Configuration
public class WebConfig implements WebMvcConfigurer {
  public void addInterceptors(InterceptorRegistry r) {
    r.addInterceptor(
        new HandlerInterceptor() {
          public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object h)
              throws Exception {
            res.setHeader("X-Content-Type-Options", "nosniff");
            if ("POST".equals(req.getMethod())) {
              var s = req.getSession(false);
              String token = req.getParameter("_csrf");
              if (s == null || token == null || !token.equals(s.getAttribute("csrf"))) {
                res.sendError(403);
                return false;
              }
            }
            return true;
          }
        });
  }
}
