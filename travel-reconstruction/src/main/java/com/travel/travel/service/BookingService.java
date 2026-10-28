package com.travel.travel.service;

import com.travel.travel.entity.*;
import com.travel.travel.repository.*;
import java.time.LocalDate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
  private final TravelRepository travels;
  private final ReservationRepository reservations;

  public BookingService(TravelRepository t, ReservationRepository r) {
    travels = t;
    reservations = r;
  }

  @Transactional
  public Reservation book(String username, Long id, int people) {
    Travel t =
        travels.lockById(id).orElseThrow(() -> new IllegalArgumentException("상품을 찾을 수 없습니다."));
    if (people < 1
        || people > t.getCapacity() - t.getReserved()
        || t.getStartDate().isBefore(LocalDate.now()))
      throw new IllegalArgumentException("예약 날짜와 잔여 인원을 확인하세요.");
    t.setReserved(t.getReserved() + people);
    Reservation r = new Reservation();
    r.setUsername(username);
    r.setTravelId(id);
    r.setPeople(people);
    return reservations.save(r);
  }

  @Transactional
  public void cancel(String username, Long id) {
    Reservation r =
        reservations.lockById(id).orElseThrow(() -> new IllegalArgumentException("예약을 찾을 수 없습니다."));
    if (!username.equals(r.getUsername())) throw new IllegalArgumentException("본인 예약만 취소할 수 있습니다.");
    Travel t = travels.lockById(r.getTravelId()).orElseThrow();
    t.setReserved(Math.max(0, t.getReserved() - r.getPeople()));
    reservations.delete(r);
  }
}
