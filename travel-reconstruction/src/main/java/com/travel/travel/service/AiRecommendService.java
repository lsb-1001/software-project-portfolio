package com.travel.travel.service;

import com.travel.travel.entity.Travel;
import java.time.LocalDate;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class AiRecommendService {
  public List<Travel> candidates(
      List<Travel> all, String style, int budget, String country, String avoid) {
    return all.stream()
        .filter(
            t ->
                t.getPrice() <= budget
                    && t.getReserved() < t.getCapacity()
                    && !t.getStartDate().isBefore(LocalDate.now()))
        .filter(t -> country.isBlank() || t.getCountry().contains(country))
        .filter(t -> avoid.isBlank() || !(t.getTitle() + " " + t.getDescription()).contains(avoid))
        .sorted(
            Comparator.<Travel>comparingInt(t -> t.getStyle().equals(style) ? 1 : 0)
                .reversed()
                .thenComparingInt(t -> Math.abs(budget - t.getPrice()))
                .thenComparing(Travel::getId))
        .limit(20)
        .toList();
  }
}
