package com.travel.travel.controller;

import com.travel.travel.entity.*;
import com.travel.travel.repository.*;
import com.travel.travel.service.*;
import jakarta.servlet.http.*;
import java.time.LocalDate;
import java.util.*;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;

@Controller
public class WebController {
  private final MemberRepository members;
  private final TravelRepository travels;
  private final ReservationRepository reservations;
  private final BookingService bookings;
  private final AiRecommendService ranker;
  private final GeminiService gemini;
  private final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder();

  public WebController(
      MemberRepository m,
      TravelRepository t,
      ReservationRepository r,
      BookingService b,
      AiRecommendService a,
      GeminiService g) {
    members = m;
    travels = t;
    reservations = r;
    bookings = b;
    ranker = a;
    gemini = g;
  }

  @ModelAttribute
  public void common(Model m, HttpSession s) {
    if (s.getAttribute("csrf") == null) s.setAttribute("csrf", UUID.randomUUID().toString());
    m.addAttribute("csrf", s.getAttribute("csrf"));
    m.addAttribute("member", s.getAttribute("loginMember"));
  }

  @GetMapping("/")
  public String home(Model m) {
    m.addAttribute("travelList", travels.findAll().stream().limit(6).toList());
    return "index";
  }

  @GetMapping("/travel/list")
  public String list(Model m) {
    m.addAttribute("travelList", travels.findAll());
    return "travel-list";
  }

  @GetMapping({"/login", "/signup"})
  public String auth(HttpServletRequest req, Model m) {
    m.addAttribute("signup", req.getRequestURI().equals("/signup"));
    return "auth";
  }

  @PostMapping("/signup")
  public String signup(@RequestParam String username, @RequestParam String password, Model m) {
    m.addAttribute("signup", true);
    if (!username.matches("[a-zA-Z0-9_]{3,30}")
        || password.length() < 8
        || password.length() > 72) {
      m.addAttribute("error", "아이디는 영문·숫자 3~30자, 비밀번호는 8~72자로 입력하세요.");
      return "auth";
    }
    Member member = new Member();
    member.setUsername(username);
    member.setPassword(passwords.encode(password));
    member.setRole("USER");
    try {
      members.save(member);
    } catch (org.springframework.dao.DataIntegrityViolationException e) {
      m.addAttribute("error", "이미 사용하는 아이디입니다.");
      return "auth";
    }
    return "redirect:/login";
  }

  @PostMapping("/login")
  public String login(
      @RequestParam String username,
      @RequestParam String password,
      HttpServletRequest req,
      Model m) {
    Member member = members.findByUsername(username);
    if (member == null || !passwords.matches(password, member.getPassword())) {
      m.addAttribute("signup", false);
      m.addAttribute("error", "아이디 또는 비밀번호를 확인하세요.");
      return "auth";
    }
    req.changeSessionId();
    req.getSession().setAttribute("loginMember", member);
    return "redirect:/";
  }

  @PostMapping("/logout")
  public String logout(HttpSession s) {
    s.invalidate();
    return "redirect:/";
  }

  @GetMapping("/recommend")
  public String form(HttpSession s) {
    return s.getAttribute("loginMember") == null ? "redirect:/login" : "recommend-form";
  }

  @PostMapping("/recommend")
  public String recommend(
      @RequestParam String style,
      @RequestParam int budget,
      @RequestParam(defaultValue = "") String country,
      @RequestParam(defaultValue = "") String avoid,
      @RequestParam(defaultValue = "") String purpose,
      Model m,
      HttpSession s) {
    if (s.getAttribute("loginMember") == null) return "redirect:/login";
    if (budget < 1 || country.length() > 50 || avoid.length() > 100 || purpose.length() > 1000)
      throw new IllegalArgumentException("입력 조건을 확인하세요.");
    var candidates = ranker.candidates(travels.findAll(), style, budget, country, avoid);
    var result = gemini.recommend(candidates, purpose);
    m.addAttribute("choices", result.choices());
    m.addAttribute("mode", result.mode());
    m.addAttribute("candidateCount", candidates.size());
    return "recommend-result";
  }

  @GetMapping("/reservation/form/{id}")
  public String booking(@PathVariable Long id, Model m, HttpSession s) {
    if (s.getAttribute("loginMember") == null) return "redirect:/login";
    m.addAttribute("travel", travels.findById(id).orElseThrow());
    return "reservation-form";
  }

  @PostMapping("/reservation/save")
  public String book(@RequestParam Long travelId, @RequestParam int people, HttpSession s) {
    Member m = (Member) s.getAttribute("loginMember");
    if (m == null) return "redirect:/login";
    bookings.book(m.getUsername(), travelId, people);
    return "redirect:/reservations";
  }

  @GetMapping("/reservations")
  public String history(Model model, HttpSession s) {
    Member m = (Member) s.getAttribute("loginMember");
    if (m == null) return "redirect:/login";
    model.addAttribute("reservations", reservations.findByUsername(m.getUsername()));
    model.addAttribute("travelMap", travelMap());
    model.addAttribute("admin", false);
    return "reservations";
  }

  @PostMapping("/reservation/cancel/{id}")
  public String cancel(@PathVariable Long id, HttpSession s) {
    Member m = (Member) s.getAttribute("loginMember");
    if (m == null) return "redirect:/login";
    bookings.cancel(m.getUsername(), id);
    return "redirect:/reservations";
  }

  private void admin(HttpSession s) {
    Member m = (Member) s.getAttribute("loginMember");
    if (m == null || !"ADMIN".equals(m.getRole()))
      throw new org.springframework.web.server.ResponseStatusException(
          org.springframework.http.HttpStatus.FORBIDDEN);
  }

  @GetMapping("/admin")
  public String adminPage(Model m, HttpSession s) {
    admin(s);
    m.addAttribute("reservations", reservations.findAll());
    m.addAttribute("travelMap", travelMap());
    m.addAttribute("admin", true);
    return "reservations";
  }

  @GetMapping("/travel/add")
  public String addForm(HttpSession s) {
    admin(s);
    return "travel-add";
  }

  @PostMapping("/travel/add")
  public String add(
      @RequestParam String title,
      @RequestParam String country,
      @RequestParam int price,
      @RequestParam String style,
      @RequestParam String description,
      @RequestParam LocalDate startDate,
      @RequestParam int capacity,
      HttpSession s) {
    admin(s);
    if (title.isBlank()
        || title.length() > 150
        || country.isBlank()
        || country.length() > 50
        || price < 1
        || capacity < 1
        || capacity > 1000
        || description.length() > 250
        || startDate.isBefore(LocalDate.now())) throw new IllegalArgumentException("상품 정보를 확인하세요.");
    Travel t = new Travel();
    t.setTitle(title);
    t.setCountry(country);
    t.setPrice(price);
    t.setStyle(style);
    t.setDescription(description);
    t.setStartDate(startDate);
    t.setCapacity(capacity);
    travels.save(t);
    return "redirect:/travel/list";
  }

  private Map<Long, Travel> travelMap() {
    Map<Long, Travel> m = new HashMap<>();
    travels.findAll().forEach(t -> m.put(t.getId(), t));
    return m;
  }

  @ExceptionHandler(IllegalArgumentException.class)
  public String invalid(IllegalArgumentException e, Model m) {
    m.addAttribute("message", e.getMessage());
    return "message";
  }
}
