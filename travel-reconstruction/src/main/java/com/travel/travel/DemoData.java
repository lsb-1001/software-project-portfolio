package com.travel.travel;

import com.travel.travel.entity.*;
import com.travel.travel.repository.*;
import java.time.LocalDate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoData implements CommandLineRunner {
  private final TravelRepository travels;
  private final MemberRepository members;

  public DemoData(TravelRepository t, MemberRepository m) {
    travels = t;
    members = m;
  }

  public void run(String... args) {
    if (travels.count() == 0) {
      String[] countries = {"일본", "한국", "대만", "베트남", "태국"},
          places = {"교토", "제주", "타이베이", "다낭", "치앙마이"},
          styles = {"힐링", "관광", "먹방", "액티비티"};
      for (int i = 0; i < 200; i++) {
        Travel t = new Travel();
        int c = i % 5;
        String style = styles[(i / 5) % 4];
        t.setTitle(places[c] + " " + style + " 여행 " + (i / 20 + 1));
        t.setCountry(countries[c]);
        t.setStyle(style);
        t.setPrice(350000 + (i % 20) * 75000);
        t.setDescription("재구현 검증용 가상 상품입니다. " + style + " 중심의 일정을 제공합니다.");
        t.setStartDate(LocalDate.now().plusDays(30 + i));
        t.setCapacity(20);
        travels.save(t);
      }
    }
    String password = System.getenv("ADMIN_PASSWORD");
    if (password != null && password.length() >= 12 && members.findByUsername("admin") == null) {
      Member m = new Member();
      m.setUsername("admin");
      m.setRole("ADMIN");
      m.setPassword(new BCryptPasswordEncoder().encode(password));
      members.save(m);
    }
  }
}
