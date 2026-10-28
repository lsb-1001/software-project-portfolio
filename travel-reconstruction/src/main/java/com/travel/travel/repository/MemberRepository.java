package com.travel.travel.repository;

import com.travel.travel.entity.Member;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MemberRepository extends JpaRepository<Member, Long> {
  Member findByUsername(String username);
}
